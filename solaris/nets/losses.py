import sys
import numpy as np
from tensorflow.keras import backend as K
from ._keras_losses import keras_losses, k_focal_loss
from ._torch_losses import torch_losses
from torch import nn


def get_loss(framework, loss, loss_weights=None):
    """Load a loss function based on a config file for the specified framework.

    Arguments
    ---------
    framework : string
        Which neural network framework to use.
    loss : dict
        Dictionary of loss functions to use.  Each key is a loss function name,
        and each entry is a (possibly-empty) dictionary of hyperparameter-value
        pairs.
    loss_weights : dict, optional
        Optional dictionary of weights for loss functions.  Each key is a loss
        function (same as in the ``loss`` argument), and the corresponding
        entry is its weight.
    """
    # lots of exception handling here. TODO: Refactor.
    if not isinstance(loss, dict):
        raise TypeError('The loss description is formatted improperly.'
                        ' See the docs for details.')
    if len(loss) > 1:

        # get the weights for each loss within the composite
        if loss_weights is None:
            # weight all losses equally
            weights = {k: 1 for k in loss.keys()}
        else:
            weights = loss_weights

        # check if sublosses dict and weights dict have the same keys
        if list(loss.keys()).sort() != list(weights.keys()).sort():
            raise ValueError(
                'The losses and weights must have the same name keys.')

        if framework == 'keras':
            return keras_composite_loss(loss, weights)
        elif framework in ['pytorch', 'torch']:
            return TorchCompositeLoss(loss, weights)

    else:  # parse individual loss functions
        loss_name, loss_dict = list(loss.items())[0]
        return get_single_loss(framework, loss_name, loss_dict)


def get_single_loss(framework, loss_name, params_dict):
    if framework == 'keras':
        if loss_name.lower() == 'focal':
            return k_focal_loss(**params_dict)
        else:
            # keras_losses in the next line is a matching dict
            # TODO: the next block doesn't handle non-focal loss functions that
            # have hyperparameters associated with them. It would be great to
            # refactor this to handle that possibility.
            if loss_name.lower() in keras_losses:
                return keras_losses.get(loss_name.lower())
            else:
                return eval(loss_name)
    elif framework in ['torch', 'pytorch']:
        if params_dict is None:
            if loss_name.lower() in torch_losses:
                return torch_losses.get(loss_name.lower())()
            else:
                return eval(loss_name)()
        else:
            if loss_name.lower() in torch_losses:
                return torch_losses.get(loss_name.lower())(**params_dict)
            else:
                return eval(loss_name)(**params_dict)


def keras_composite_loss(loss_dict, weight_dict):
    """Wrapper to other loss functions to create keras-compatible composite."""

    def composite(y_true, y_pred):
        loss = K.sum(K.flatten(K.stack([weight_dict[loss_name]*get_single_loss(
                'keras', loss_name, loss_params)(y_true, y_pred)
                for loss_name, loss_params in loss_dict.items()], axis=-1)))
        return loss

    return composite


class TorchCompositeLoss(nn.Module):
    """Composite loss function."""

    def __init__(self, loss_dict, weight_dict=None):
        """Create a composite loss function from a set of pytorch losses."""
        super().__init__()
        self.weights = weight_dict
        self.losses = {loss_name: get_single_loss('pytorch',
                                                  loss_name,
                                                  loss_params)
                       for loss_name, loss_params in loss_dict.items()}
        self.values = {}  # values from the individual loss functions

    def forward(self, outputs, targets):
        loss = 0
        for func_name, weight in self.weights.items():
            self.values[func_name] = self.losses[func_name](outputs, targets)
            loss += weight*self.values[func_name]

        return loss
