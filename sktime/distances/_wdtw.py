# -*- coding: utf-8 -*-
__author__ = ["chrisholder", "TonyBagnall"]

import warnings
from typing import Any

import numpy as np
from numba import njit
from numba.core.errors import NumbaWarning

from sktime.distances.base import DistanceCallable, NumbaDistance
from sktime.distances.lower_bounding import resolve_bounding_matrix

# Warning occurs when using large time series (i.e. 1000x1000)
warnings.simplefilter("ignore", category=NumbaWarning)


class _WdtwDistance(NumbaDistance):
    r"""Weighted dynamic time warping (WDTW) distance between two time series.

    WDTW uses DTW with a weighted pairwise distance matrix rather than a window. When
    creating the distance matrix :math:'M', a weight penalty  :math:'w_{|i-j|}' for a
    warping distance of :math:'|i-j|' is applied, so that for series
    :math:'a = <a_1, ..., a_m>' and :math:'b=<b_1,...,b_m>',
    .. math:: M_{i,j}=  w(|i-j|) (a_i-b_j)^2.
    A logistic weight function, proposed in [1] is used, so that a warping of :math:'x'
    places imposes a weighting of
    .. math:: w(x)=\frac{w_{max}}{1+e^{-g(x-m/2)}},
    where :math:'w_{max}' is an upper bound on the weight (set to 1), :math:'m' is
    the series length and :math:'g' is a parameter that controls the penalty level
    for larger warpings. The greater :math:'g' is, the greater the penalty for warping.
    Once :math:'M' is found, standard dynamic time warping is applied.

    WDTW is set up so you can use it with a bounding box in addition to the weight
    function is so desired. This is for consistency with the other distance functions.

    References
    ----------
    ..[1] Jeong, Y., Jeong, M., Omitaomu, O.: Weighted dynamic time warping for time
    series classification. Pattern Recognition 44, 2231–2240 (2011)
    """

    def _distance_factory(
        self,
        x: np.ndarray,
        y: np.ndarray,
        window: int = None,
        itakura_max_slope: float = None,
        bounding_matrix: np.ndarray = None,
        g: float = 0.05,
        **kwargs: Any,
    ) -> DistanceCallable:
        """Create a no_python compiled wdtw distance callable.

        Parameters
        ----------
        x: np.ndarray (2d array of shape (d,m1)).
            First time series.
        y: np.ndarray (2d array of shape (d,m2)).
            Second time series.
        window: float, defaults = None
            Integer that is the radius of the sakoe chiba window (if using Sakoe-Chiba
            lower bounding). Must be between 0 and 1.
        itakura_max_slope: float, defaults = None
            Gradient of the slope for itakura parallelogram (if using Itakura
            Parallelogram lower bounding). Must be between 0 and 1.
        bounding_matrix: np.ndarray (2d array of shape (m1,m2)), defaults = None
            Custom bounding matrix to use. If defined then other lower_bounding params
            are ignored. The matrix should be structure so that indexes considered in
            bound should be the value 0. and indexes outside the bounding matrix should
            be infinity.
        g: float, defaults = 0.
            Constant that controls the curvature (slope) of the function; that is, g
            controls the level of penalisation for the points with larger phase
            difference.
        kwargs: Any
            Extra kwargs.


        Returns
        -------
        Callable[[np.ndarray, np.ndarray], float]
            No_python compiled wdtw distance callable.

        Raises
        ------
        ValueError
            If the input time series are not numpy array.
            If the input time series do not have exactly 2 dimensions.
            If the sakoe_chiba_window_radius is not an integer.
            If the itakura_max_slope is not a float or int.
            If the value of g is not a float
        """
        _bounding_matrix = resolve_bounding_matrix(
            x, y, window, itakura_max_slope, bounding_matrix
        )

        if not isinstance(g, float):
            raise ValueError(
                f"The value of g must be a float. The current value is {g}"
            )

        @njit(cache=True)
        def numba_wdtw_distance(
            _x: np.ndarray,
            _y: np.ndarray,
        ) -> float:
            cost_matrix = _weighted_cost_matrix(_x, _y, _bounding_matrix, g)
            return cost_matrix[-1, -1]

        return numba_wdtw_distance


@njit(cache=True)
def _weighted_cost_matrix(
    x: np.ndarray, y: np.ndarray, bounding_matrix: np.ndarray, g: float
):
    """Compute the wdtw cost matrix between two time series.

    Parameters
    ----------
    x: np.ndarray (2d array)
        First timeseries.
    y: np.ndarray (2d array)
        Second timeseries.
    bounding_matrix: np.ndarray (2d of size mxn where m is len(x) and n is len(y))
        Bounding matrix where the values in bound are marked by finite values and
        outside bound points are infinite values.
    g: float
        Constant that controls the curvature (slope) of the function; that is, g
        controls the level of penalisation for the points with larger phase difference.

    Returns
    -------
    np.ndarray
        Weighted cost matrix between x and y time series.
    """
    dimensions = x.shape[0]
    x_size = x.shape[1]
    y_size = y.shape[1]
    cost_matrix = np.full((x_size + 1, y_size + 1), np.inf)
    cost_matrix[0, 0] = 0.0

    weight_vector = np.array(
        [1 / (1 + np.exp(-g * (i - x_size / 2))) for i in range(0, x_size)]
    )

    for i in range(x_size):
        for j in range(y_size):
            if np.isfinite(bounding_matrix[i, j]):
                sum = 0
                for k in range(dimensions):
                    sum += (x[k][i] - y[k][j]) * (x[k][i] - y[k][j])
                cost_matrix[i + 1, j + 1] = (
                    min(cost_matrix[i, j + 1], cost_matrix[i + 1, j], cost_matrix[i, j])
                    + weight_vector[np.abs(i - j)] * sum
                )

    return cost_matrix[1:, 1:]
