"""Deprecated. The classes have moved to :mod:`mt.base.model` of package `mtbase`.

This shim only re-exports them so that existing imports and pickles keep working.
"""

from mt import logg

logg.logger.warn_module_move("mt.tfc", "mt.base.model")

from mt.base.model import (
    TensorError,
    ModelSyntaxError,
    ModelParams,
    MHAParams,
    MHAPool2DCascadeParams,
    MobileNetV3MixerParams,
    ClassifierParams,
    NameScope,
)

__all__ = [
    "TensorError",
    "ModelSyntaxError",
    "ModelParams",
    "MHAParams",
    "MHAPool2DCascadeParams",
    "MobileNetV3MixerParams",
    "ClassifierParams",
    "NameScope",
]
