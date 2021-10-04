'''BeeHive concurrency using asyncio and multiprocessing.

This is a concurrency model made up by Minh-Tri. In this model, there is main process called the
queen bee and multiple subprocesses called worker bees. The queen bee is responsible for spawning
and destroying worker bees herself. She is also responsible for organisation-level tasks. She does
not do individual-level tasks but instead assigns those tasks to worker bees.

The BeeHive model can be useful for applications like making ML model predictions from a dataframe.
In this case, the queen bee owns access to the ML model and the dataframe, delegates the
potentially IO-related preprocessing and postprocessing tasks of every row of the dataframe to
worker bees, and deals with making batch predictions from the model.
'''

from typing import Optional

import queue
import multiprocessing as mp

from ..contextlib import nullcontext


__all__ = ['Bee', 'WorkerBee', 'subprocess_worker_bee', 'QueenBee', 'beehive_run']


class Bee:
    '''The base class of a bee.

    A bee is an asynchronous multi-tasking worker that can communicate with its parent and zero or
    more child bees via message passing. Communication means executing a task for the parent and
    delegating child bees to do subtasks. All tasks are asynchronous.

    Each bee maintains a private communication its parent via two queues `p_p2m` and `p_m2q`, which
    stand for parent-to-me queue and me-to-parent queue. It also has 2 common queues to be shared
    among the children for task scheduling, denoted as `ts_m2c` and `ts_c2m`, which stand for
    me-to-child and child-to-me queues. The bee places on `ts_m2c` a zero-based task id. Its
    children fight against each other to grab a task from `ts_m2c` and places '(task_id, child_id)'
    on `ts_c2m` to let the parent bee know which child bee will process the task. The communication
    revolving the task will be conducted via the one-to-one channel between the parent bee and the
    child bee who has volunteered for the task. The communication is divided into 2 messages, each
    of which is a key-value dictionary.

    The first message is sent from the parent bee describing the task to be delegated to the child
    `{'msg_type': 'task_info', 'task_id': int, 'name': str, 'args': tuple, 'kwargs': dict}`.
    Variables `name` is the task name. It is expected that the child bee class implements an asyn
    member function of the same name as the task name to handle the task. Variables `args` and
    `kwargs` will be passed as positional and keyword arguments respectively to the function. The
    parent assumes that the child will process the task asynchronously at some point in time, and
    awaits for response.

    Upon finishing processing the task, either successfully or not, the child bee must send
    `{'msg_type': 'task_done', 'task_id': int, 'status': str, ...}` back to the parent bee.
    `status` can be one of 3 values: 'cancelled', 'raised' and 'succeeded', depending on whether
    the task was cancelled, raised an exception, or succeeded without any exception. If `status` is
    'cancelled', key `reason` tells the reason if it is not None. If `status` is 'raised', key
    `exception` contains an Exception instance and key `traceback` contains a list of text lines
    describing the call stack, and key `other_details` contains other supporting information.
    Finally, if `status` is 'succeeded', key `returning_value` holds the returning value.

    Child bees are run in daemon subprocesses of the parent bee process. There are some special
    messages apart from messages controlling task delegation above. The first one is
    `{'msg_type': 'dead', 'death_type': str, ...}` sent from a child bee to its parent, where
    `death_type` is either 'normal' or 'killed'. If it is 'normal', key `exit_code` is either None
    or a value representing an exit code or a last word. If it is 'killed', key `exception` holds
    the Exception that caused the bee to be killed, and key `traceback` holds a list of text lines
    describing the call stack. This message is sent only when the bee has finished up tasks and its
    worker process is about to terminate. The second one is `{'msg_type': 'die'}` sent from a
    parent bee to one of its children, telling the child bee to finish its life gracecfully. Bees
    are very sensitive, if the parent says 'die' they become very sad, stop accepting new tasks,
    and die as soon as all existing tasks have been done.

    Each bee comes with its own life cycle, implemented in the async :func:`run`. The user should
    not have to override any private member function. They just have to create new asyn member
    functions representing different tasks.

    Parameters
    ----------
    p_p2m : queue.Queue
        the parent-to-me queue for private communication
    p_m2p : queue.Queue
        the me-to-parent queue for private communication
    child_id : int
        the bee's id seen in the eyes of its parent
    ts_p2m : queue.Queue
        the parent-to-me queue for task scheduling
    ts_m2p : queue.Queue
        the me-to-parent queue for task scheduling
    max_concurrency : int
        maximum number of concurrent tasks that the bee handles at a time
    '''


    def __init__(
            self,
            p_p2m: queue.Queue,
            p_m2p: queue.Queue,
            child_id: int,
            ts_p2m: queue.Queue,
            ts_m2p: queue.Queue,
            max_concurrency: int = 1024,
    ):
        import multiprocessing as mp

        self.p_p2m = p_p2m # parent-to-me, private
        self.p_m2p = p_m2p # me-to-parent, private
        self.child_id = child_id
        self.ts_p2m = ts_p2m # parent-to-me, task scheduling
        self.ts_m2p = ts_m2p # me-to-parent, task scheduling

        self.child_comm_list = []
        self.child_alive_list = []
        if not isinstance(max_concurrency, int):
            raise ValueError("Argument 'max_concurrency' is not an integer: {}.".format(max_concurrency))
        self.max_concurrency = max_concurrency

        # task scheduling
        self.ts_m2c = mp.Queue() # me-to-children
        self.ts_c2m = mp.Queue() # children-to-me
        self.task2child_map = {} # task_id -> child_id, orders that have been acknowledged but not yet awaited by the parent bee
        self.task_id_cnt = 0 # task id counter


    # ----- public -----


    async def run(self):
        '''Implements the life-cycle of the bee. Invoke this function only once.'''
        await self._run_initialise()
        while (not self.to_terminate) or (self.pending_task_cnt > 0) or self.working_task_map:
            await self._run_inloop()
        await self._run_finalise()


    async def delegate(self, name: str, *args, **kwargs):
        '''Delegates a task to one of child bees and awaits the result.

        Parameters
        ----------
        name : str
            the name of the task/asyn member function of the child bee class responsible for
            handling the task
        args : tuple
            positional arguments to be passed as-is to the task/asyn member function
        kwargs : dict
            keyword arguments to be passed as-is to the task/asyn member function

        Returns
        -------
        task_result : dict
            returning message in the form `{'status': str, ...}` where `status` is one of
            'cancelled', 'raised' and 'succeeded'. The remaining keys are described in the class
            docstring.
        child_id : int
            the id of the child that has executed the task
        '''

        import asyncio

        # generate new task id
        task_id = self.task_id_cnt
        self.task_id_cnt += 1

        # place an order
        self.ts_m2c.put_nowait(task_id)

        # wait for a child bee to accept the order
        while task_id not in self.task2child_map:
            await asyncio.sleep(0.001) # await changes elsewhere

        child_id = self.task2child_map.pop(task_id)

        # send the task info to the child
        p_m2c, p_c2m = self.child_comm_list[child_id]
        p_m2c.put_nowait({
            'msg_type': 'task_info',
            'task_id': task_id,
            'name': name,
            'args': args,
            'kwargs': kwargs,
        })
        self.started_dtask_map[task_id] = child_id

        # wait for the child bee to finish the specified task (it can concurrently do other tasks)
        while task_id not in self.done_dtask_map:
            await asyncio.sleep(0.001) # await changes elsewhere

        msg = self.done_dtask_map.pop(task_id)

        return msg, child_id


    # ----- private -----


    def _add_new_child(self, p_m2c: queue.Queue, p_c2m: queue.Queue):
        '''Adds a new child to the bee.'''

        child_id = len(self.child_comm_list)
        self.child_comm_list.append((p_m2c, p_c2m))
        self.child_alive_list.append(True) # the new child is assumed alive


    async def _run_initialise(self):
        '''Initialises the life cycle of the bee.'''

        import asyncio

        self.to_terminate = False # let other futures decide when to terminate

        # tasks delegated to child bees
        self.started_dtask_map = {} # task_id -> child_id
        self.done_dtask_map = {} # task_id -> {'status': str, ...}

        # tasks handled by the bee itself
        self.pending_task_cnt = 0 # number of tasks awaiting further info
        self.working_task_map = {} # task -> task_id

        self.listening_task = asyncio.ensure_future(self._listen_and_dispatch())


    async def _run_inloop(self):
        '''The thing that the bee does every day until it dies.'''

        import asyncio

        # await for some tasks to be done
        if self.working_task_map:
            done_task_set, _ = await asyncio.wait(self.working_task_map.keys(), timeout=0.1, return_when=asyncio.FIRST_COMPLETED)

            # process each of the tasks done by the bee
            for task in done_task_set:
                self._deliver_done_task(task)
        else:
            await asyncio.sleep(0.1)


    async def _run_finalise(self):
        '''Finalises the life cycle of the bee.'''

        import asyncio

        self.stop_listening = True
        await asyncio.wait([self.listening_task])
        self._inform_death({'death_type': 'normal', 'exit_code': self.exit_code})


    async def _execute_task(self, name: str, args: tuple = (), kwargs: dict = {}):
        '''Processes a request message coming from one of the parent bee.

        Parameters
        ----------
        name : str
            name of the task/asyn member function to be invoked
        args : tuple
            positional arguments to be passed to the task as-is
        kwargs : dict
            keyword arguments to be passed to the task as-is

        Returns
        -------
        object
            user-defined

        Raises
        ------
        Exception
            user-defined
        '''
        func = getattr(self, name)
        return await func(*args, **kwargs)


    def _mourn_death(self, child_id, msg): # msg = {'death_type': str, ...}
        '''Processes the death wish of a child bee.'''

        from ..traceback import extract_stack_compact

        self.child_alive_list[child_id] = False # mark the child as dead

        # process all pending tasks held up by the dead bee
        for task_id in self.started_dtask_map:
            if child_id != self.started_dtask_map[task_id]:
                continue
            del self.started_dtask_map[task_id] # pop it
            self.done_dtask_map[task_id] = {
                'status': 'raised',
                'exception': RuntimeError('Delegated task cancelled as the delegated bee has been killed.'),
                'traceback': extract_stack_compact(),
                'other_details': {
                    'child_id': child_id,
                    'last_word_msg': msg,
                },
            }


    def _deliver_done_task(self, task):
        '''Sends the result of a task that has been done by the bee back to its parent.'''

        task_id = self.working_task_map.pop(task)

        if task.cancelled():
            self.p_m2p.put_nowait({'msg_type': 'task_done', 'task_id': task_id, 'status': 'cancelled', 'reason': None})
            #print("task_cancelled")
        elif task.exception() is not None:
            #print("task_raised")
            msg = {
                'msg_type': 'task_done',
                'task_id': task_id,
                'status': 'raised',
                'exception': task.exception(),
                'traceback': task.get_stack(),
                'other_details': None,
            }
            #print("msg=",msg)
            self.p_m2p.put_nowait(msg)
        else:
            #print("task_done")
            self.p_m2p.put_nowait({
                'msg_type': 'task_done',
                'task_id': task_id,
                'status': 'succeeded',
                'returning_value': task.result(),
            })


    def _dispatch_new_child_msg(self, child_id, msg):
        '''Dispatches a new message from a child.'''

        from ..traceback import extract_stack_compact

        msg_type = msg['msg_type']
        if msg_type == 'dead':
            self._mourn_death(child_id, msg)
        elif msg_type == 'task_done': # delegated task done
            task_id = msg['task_id']
            status = msg['status']
            child_id = self.started_dtask_map.pop(task_id)
            #print("result: child_id={}, task_id={} for {}".format(child_id, task_id, self))
            if status == 'cancelled':
                self.done_dtask_map[task_id] = {
                    'status': 'raised',
                    'exception': RuntimeError('Delegated task cancelled.'),
                    'traceback': extract_stack_compact(),
                    'other_details': {'child_id': child_id, 'reason': msg['reason']},
                }
            elif status == 'raised':
                self.done_dtask_map[task_id] = {
                    'status': 'raised',
                    'exception': RuntimeError('Delegated task raised an exception.'),
                    'traceback': extract_stack_compact(),
                    'other_details': {'child_id': child_id, 'msg': msg},
                }
            else:
                self.done_dtask_map[task_id] = {
                    'status': 'succeeded',
                    'returning_value': msg['returning_value'],
                }
        else:
            self.to_terminate = True
            self.exit_code = "Unknown message with type '{}'.".format(msg_type)


    def _dispatch_new_parent_msg(self, msg):
        '''Dispatches a new message from the parent.'''

        import asyncio

        from ..traceback import extract_stack_compact

        msg_type = msg['msg_type']
        if msg_type == 'die': # request to die?
            self.to_terminate = True
            self.exit_code = "The parent bee ordered to die gracefully."
        elif msg_type == 'task_info': # task info -> new task
            self.pending_task_cnt -= 1
            task_id = msg['task_id']
            task = asyncio.ensure_future(self._execute_task(name=msg['name'], args=msg['args'], kwargs=msg['kwargs']))
            self.working_task_map[task] = task_id
        else:
            self.to_terminate = True
            self.exit_code = "Unknown message with type '{}'.".format(msg_type)


    async def _listen_and_dispatch(self):
        '''Listens to new messages regularly and dispatches them.'''

        import asyncio
        import queue

        self.stop_listening = False # let other futures decide when to stop listening
        while not self.stop_listening:
            dispatched = False

            # listen to the parent's private comm
            if not self.p_p2m.empty(): # has data?
                msg = self.p_p2m.get_nowait()
                self._dispatch_new_parent_msg(msg)
                dispatched = True

            # listen to the parent's task queue if we are free
            if (not self.to_terminate) and\
               len(self.working_task_map) + self.pending_task_cnt < self.max_concurrency:
                try:
                    task_id = self.ts_p2m.get_nowait()
                    self.ts_m2p.put_nowait((task_id, self.child_id)) # notify the parent
                    self.pending_task_cnt += 1 # awaiting further info
                except queue.Empty:
                    pass

            # listen to the task scheduler
            if not self.ts_c2m.empty(): # has data?
                task_id, child_id = self.ts_c2m.get()
                self.task2child_map[task_id] = child_id
                dispatched = True

            # listen to each child's private comm
            #print("listening:", self)
            for child_id, comm in enumerate(self.child_comm_list):
                if not self.child_alive_list[child_id]:
                    continue
                p_m2c, p_c2m = comm
                if not p_c2m.empty(): # has data?
                    msg = p_c2m.get_nowait()
                    self._dispatch_new_child_msg(child_id, msg)
                    dispatched = True

            if not dispatched: # has not dispatched anything?
                await asyncio.sleep(0.1) # sleep a bit


    def _inform_death(self, msg):
        '''Informs the parent bee that it has died.

        Parameters
        ----------
        msg : dict
            message in the form `{'death_type': str, ...}` where death type can be either 'normal' or 'killed'
        '''

        wrapped_msg = {'msg_type': 'dead'}
        wrapped_msg.update(msg)
        self.p_m2p.put_nowait(wrapped_msg)


class WorkerBee(Bee):
    '''A worker bee in the BeeHive concurrency model.

    See parent :class:`Bee` for more details.

    Parameters
    ----------
    p_p2m : queue.Queue
        the parent-to-me queue for private communication
    p_m2p : queue.Queue
        the me-to-parent queue for private communication
    child_id : int
        the bee's id seen in the eyes of its parent
    ts_p2m : multiprocessing.Queue
        the parent-to-me queue for task scheduling
    ts_m2p : multiprocessing.Queue
        the me-to-parent queue for task scheduling
    max_concurrency : int
        maximum number of concurrent tasks that the bee handles at a time
    context_vars : dict
        a dictionary of context variables within which the function runs. It must include
        `context_vars['async']` to tell whether to invoke the function asynchronously or not.
        In addition, variable 's3_client' must exist and hold an enter-result of an async with
        statement invoking :func:`mt.base.s3.create_s3_client`.
    '''

    def __init__(
            self,
            p_p2m: mp.Queue,
            p_m2p: mp.Queue,
            child_id: int,
            ts_p2m: mp.Queue,
            ts_m2p: mp.Queue,
            max_concurrency: int = 1024,
            context_vars: dict = {},
    ):
        super().__init__(p_p2m, p_m2p, child_id, ts_p2m, ts_m2p, max_concurrency=max_concurrency)
        self.context_vars = context_vars


    # ----- public -----


    async def busy_status(self, context_vars: dict = {}):
        '''A task to check how busy the worker bee is.

        Parameters
        ----------
        context_vars : dict
            a dictionary of context variables within which the function runs. It must include
            `context_vars['async']` to tell whether to invoke the function asynchronously or not.
            In addition, variable 's3_client' must exist and hold an enter-result of an async with
            statement invoking :func:`mt.base.s3.create_s3_client`.

        Returns
        -------
        float
            a scalar between 0 and 1 where 0 means completely free and 1 means completely busy
        '''
        return (len(self.working_task_map) + self.pending_task_cnt) / self.max_concurrency


    # ----- private -----


    async def _execute_task(self, name: str, args: tuple = (), kwargs: dict = {}):
        new_kwargs = {'context_vars': self.context_vars}
        new_kwargs.update(kwargs)
        return await super()._execute_task(name, args, new_kwargs)
    _execute_task.__doc__ = Bee._execute_task.__doc__


def subprocess_worker_bee(
        workerbee_class,
        child_id: int,
        ts_p2m: mp.Queue,
        ts_m2p: mp.Queue,
        init_args: tuple = (),
        init_kwargs: dict = {},
        s3_profile: Optional[str] = None,
        max_concurrency: int = 1024,
):
    '''Creates a daemon subprocess that holds a worker bee and runs the bee in the subprocess.

    Parameters
    ----------
    workerbee_class : class
        subclass of :class:`WorkerBee` whose constructor accepts all positional and keyword
        arguments of the constructor of the super class
    child_id : int
        the bee's id seen in the eyes of its parent
    ts_p2m : multiprocessing.Queue
        the parent-to-me queue for task scheduling
    ts_m2p : multiprocessing.Queue
        the me-to-parent queue for task scheduling
    init_args : tuple
        additional positional arguments to be passed as-is to the new bee's constructor
    init_kwargs : dict
        additional keyword arguments to be passed as-is to the new bee's constructor
    s3_profile : str, optional
        the S3 profile from which the context vars are created.
        See :func:`mt.base.s3.create_context_vars`.
    max_concurrency : int
        maximum number of concurrent tasks that the bee handles at a time

    Returns
    -------
    process : multiprocessing.Process
        the created subprocess
    p_p2m : queue.Queue
        the parent-to-me queue for private communication with the worker bee
    p_m2p : queue.Queue
        the me-to-parent queue for private communication with the worker bee
    '''

    import multiprocessing as mp

    async def subprocess_asyn(
            workerbee_class,
            p_p2m: mp.Queue,
            p_m2p: mp.Queue,
            child_id: int,
            ts_p2m: mp.Queue,
            ts_m2p: mp.Queue,
            init_args: tuple = (),
            init_kwargs: dict = {},
            s3_profile: Optional[str] = None,
            max_concurrency: int = 1024,
    ):
        from ..s3 import create_context_vars

        async with create_context_vars(profile=s3_profile, asyn=True) as context_vars:
            bee = workerbee_class(p_p2m, p_m2p, child_id, ts_p2m, ts_m2p, *init_args, max_concurrency=max_concurrency, context_vars=context_vars, **init_kwargs)
            await bee.run()

    def subprocess(
            workerbee_class,
            p_p2m: mp.Queue,
            p_m2p: mp.Queue,
            child_id: int,
            ts_p2m: mp.Queue,
            ts_m2p: mp.Queue,
            init_args: tuple = (),
            init_kwargs: dict = {},
            s3_profile: Optional[str] = None,
            max_concurrency: int = 1024,
    ):
        import asyncio
        from ..traceback import extract_stack_compact

        try:
            asyncio.run(subprocess_asyn(workerbee_class, p_p2m, p_m2p, child_id, ts_p2m, ts_m2p, init_args=init_args, init_kwargs=init_kwargs, s3_profile=s3_profile, max_concurrency=max_concurrency))
        except Exception as e: # tell the queen bee that the worker bee has been killed by an unexpected exception
            msg = {
                'msg_type': 'dead',
                'death_type': 'killed',
                'exception': e,
                'traceback': extract_stack_compact(),
            }
            #print("WorkerBee exception msg", msg)
            p_m2p.put_nowait(msg)

    p_p2m = mp.Queue()
    p_m2p = mp.Queue()
    process = mp.Process(
        target=subprocess,
        args=(workerbee_class, p_p2m, p_m2p, child_id, ts_p2m, ts_m2p),
        kwargs={'init_args': init_args, 'init_kwargs': init_kwargs, 's3_profile': s3_profile, 'max_concurrency': max_concurrency},
        daemon=True)
    process.start()

    return process, p_p2m, p_m2p


class QueenBee(WorkerBee):
    '''The queen bee in the BeeHive concurrency model.

    The queen bee and her worker bees work in asynchronous mode. Each worker bee operates within a
    context returned from :func:`mt.base.s3.create_context_vars`, with a given profile. It is asked
    to upper-limit number of concurrent asyncio tasks to a given threshold.

    The queen bee herself is a worker bee. However, initialising a queen bee, the user must provide
    a subclass of :class:`WorkerBee` to represent the worker bee class, from which the queen can
    spawn worker bees. Like other bees, it is expected that the user write member asynchornous
    functions to handle tasks.

    Parameters
    ----------
    p_p2m : queue.Queue
        the parent-to-me queue for private communication between the user (parent) and the queen
    p_m2p : queue.Queue
        the me-to-parent queue for private communication between the user (parent) and the queen
    child_id : int
        the queen bee's id seen in the eyes of the user
    ts_p2m : queue.Queue
        the parent-to-me queue for task scheduling
    ts_m2p : queue.Queue
        the me-to-parent queue for task scheduling
    worker_bee_class : class
        subclass of :class:`WorkerBee` whose constructor accepts all positional and keyword
        arguments of the constructor of the super class
    worker_init_args : tuple
        additional positional arguments to be passed as-is to each new worker bee's constructor
    worker_init_kwargs : dict
        additional keyword arguments to be passed as-is to each new worker bee's constructor
    s3_profile : str, optional
        the S3 profile from which the context vars are created. See :func:`mt.base.s3.create_context_vars`.
    max_concurrency : int
        the maximum number of concurrent tasks at any time for a worker bee, good for managing
        memory allocations. Non-integer values are not accepted.
    context_vars : dict
        a dictionary of context variables within which the queen be functions runs. It must include
        `context_vars['async']` to tell whether to invoke the function asynchronously or not.
        In addition, variable 's3_client' must exist and hold an enter-result of an async with
        statement invoking :func:`mt.base.s3.create_s3_client`.
    '''

    def __init__(
            self,
            p_p2m: queue.Queue,
            p_m2p: queue.Queue,
            child_id: int,
            ts_p2m: queue.Queue,
            ts_m2p: queue.Queue,
            worker_bee_class,
            worker_init_args: tuple = (),
            worker_init_kwargs: dict = {},
            s3_profile: Optional[str] = None,
            max_concurrency: int = 1024,
            context_vars: dict = {},
    ):
        super().__init__(p_p2m, p_m2p, child_id, ts_p2m, ts_m2p, max_concurrency=max_concurrency, context_vars=context_vars)

        self.worker_bee_class = worker_bee_class
        self.worker_init_args = worker_init_args
        self.worker_init_kwargs = worker_init_kwargs
        self.s3_profile = s3_profile

        # the processes of existing workers, excluding those that are dead
        self.process_map = {} # worker_id/child_id -> process


    # ----- private -----


    async def _manage_population(self):
        '''Manages the population of worker bees regularly.'''

        import asyncio
        import multiprocessing as mp

        from .base import used_cpu_too_much, used_memory_too_much

        min_num_workers = 1
        max_num_workers = max(mp.cpu_count()-1, min_num_workers)

        self.stop_managing = False # let other futures decide when to stop managing
        while not self.stop_managing:
            num_workers = len(self.child_comm_list)

            if num_workers < min_num_workers:
                self._spawn_new_worker_bee()
            elif (num_workers > min_num_workers) and ((num_workers > max_num_workers) or used_cpu_too_much() or used_memory_too_much()):
                # kill the worker bee that responds to 'busy_status' task
                task_result, worker_id = await self.delegate('busy_status')
                p_m2c, p_c2m = self.child_comm_list[worker_id]
                p_m2c.put_nowait({'msg_type': 'die'})
            elif num_workers < max_num_workers:
                self._spawn_new_worker_bee()

            await asyncio.sleep(10) # sleep for 10 seconds


    def _mourn_death(self, child_id, msg): # msg = {'death_type': str, ...}
        super()._mourn_death(child_id, msg)
        self.process_map.pop(child_id)
    _mourn_death.__doc__ = WorkerBee._mourn_death.__doc__


    def _spawn_new_worker_bee(self):
        worker_id = len(self.child_comm_list) # get new worker id
        process, p_m2c, p_c2m = subprocess_worker_bee(
            self.worker_bee_class,
            worker_id,
            self.ts_m2c,
            self.ts_c2m,
            init_args=self.worker_init_args,
            init_kwargs=self.worker_init_kwargs,
            s3_profile=self.s3_profile,
            max_concurrency=self.max_concurrency)
        self._add_new_child(p_m2c, p_c2m)
        self.process_map[worker_id] = process
        return worker_id


    async def _run_initialise(self):
        await super()._run_initialise()
        import asyncio
        self.managing_task = asyncio.ensure_future(self._manage_population())


    async def _run_finalise(self):
        import asyncio

        # ask every worker bee to die gracefully
        for worker_id in self.process_map:
            p_m2c, p_c2m = self.child_comm_list[worker_id]
            p_m2c.put_nowait({'msg_type': 'die'})

        # await until every worker bee has died
        while self.process_map:
            await asyncio.sleep(0.01)

        self.stop_managing = True
        await asyncio.wait([self.managing_task])

        await super()._run_finalise()


async def beehive_run(
        queenbee_class,
        workerbee_class,
        task_name: str,
        task_args: tuple = (),
        task_kwargs: dict = {},
        s3_profile: Optional[str] = None,
        max_concurrency: int = 1024,
        context_vars: dict = {},
        logger=None):
    '''An asyn function that runs a task in a BeeHive concurrency model.

    Parameters
    ----------
    queenbee_class : class
        a subclass of :class:`QueenBee`
    workerbee_class : class
        a subclass of :class:WorkerBee`
    task_name : str
        name of a task assigned to the queen bee, and equivalently the queen bee's member asyn
        function handling the task
    task_args : tuple
        positional arguments to be passed to the member function as-is
    task_kwargs : dict
        keyword arguments to be passed to the member function as-is
    s3_profile : str, optional
        the S3 profile from which the context vars are created. See
        :func:`mt.base.s3.create_context_vars`.
    max_concurrency : int
        maximum number of concurrent tasks that the bee handles at a time
    context_vars : dict
        a dictionary of context variables within which the function runs. It must include
        `context_vars['async']` to tell whether to invoke the function asynchronously or not.
        In addition, variable 's3_client' must exist and hold an enter-result of an async with
        statement invoking :func:`mt.base.s3.create_s3_client`.
    logger : logging.Logger or equivalent
        logger for debugging purposes

    Returns
    -------
    object
        anything returned by the task assigned to the queen bee

    Raises
    ------
    RuntimeError
        when the queen bee has cancelled her task
    Exception
        anything raised by the task assigned to the queen bee
    '''

    if not context_vars['async']:
        raise ValueError("The function can only be run in asynchronous mode.")

    import multiprocessing as mp
    import asyncio

    # create a private communication channel with the queen bee
    p_u2q = queue.Queue()
    p_q2u = queue.Queue()

    # task-scheduling queues to communicate with the queen bee
    ts_u2q = queue.Queue()
    ts_q2u = queue.Queue()

    # create a queen bee and start her life
    queen = queenbee_class(
        p_u2q,
        p_q2u,
        0,
        ts_u2q,
        ts_q2u,
        workerbee_class,
        s3_profile=s3_profile,
        max_concurrency=max_concurrency,
        context_vars=context_vars
    )
    queen_life = asyncio.ensure_future(queen.run())

    # advertise a task to the queen bee and waits for her response
    task_id = 0
    ts_u2q.put_nowait(task_id)
    while ts_q2u.empty():
        await asyncio.sleep(0.001)
    
    # describe the task to her
    p_u2q.put_nowait({
        'msg_type': 'task_info',
        'task_id': 0,
        'name': task_name,
        'args': task_args,
        'kwargs': task_kwargs,
    })

    # wait for the task to be done
    while p_q2u.empty():
        await asyncio.sleep(0.1)

    # get the result
    msg = p_q2u.get_nowait()

    # tell the queen to die
    p_u2q.put_nowait({'msg_type': 'die'})

    # wait for her to die, hopefully gracefully
    await asyncio.wait([queen_life])

    # intepret the result
    #print("msg to heaven", msg)
    if msg['status'] == 'cancelled':
        raise RuntimeError("The queen bee cancelled the task. Reason: {}".format(msg['reason']))

    if msg['status'] == 'raised':
      with logger.scoped_debug("Exception raised by the queen bee", curly=False) if logger else nullcontext():
        with logger.scoped_debug("Traceback", curly=False) if logger else nullcontext():
            logger.debug(msg['traceback'])
        with logger.scoped_debug("Other details", curly=False) if logger else nullcontext():
            logger.debug(msg['other_details'])
        raise msg['exception']

    else: # msg['status'] == done'
        return msg['returning_value']
