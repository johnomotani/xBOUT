import collections

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

import xarray as xr

from .utils import (_create_norm, _decompose_regions, _is_core_only, plot_separatrices,
                    plot_targets)


def regions(da, ax=None, **kwargs):
    """
    Plots each logical plotting region as a different color for debugging.

    Uses matplotlib.pcolormesh
    """

    x = kwargs.pop('x', 'R')
    y = kwargs.pop('y', 'Z')

    if len(da.dims) != 2:
        raise ValueError("da must be 2D (x,y)")

    if ax is None:
        fig, ax = plt.subplots()

    regions = _decompose_regions(da)

    colored_regions = [xr.full_like(region, fill_value=num / len(regions))
                       for num, region in enumerate(regions)]

    return [region.plot.pcolormesh(x=x, y=y, vmin=0, vmax=1, cmap='tab20',
                                   infer_intervals=False, add_colorbar=False, ax=ax,
                                   **kwargs)
            for region in colored_regions]


def plot2d_wrapper(da, method, *, ax=None, separatrix=True, targets=True,
                   add_limiter_hatching=True, gridlines=None, cmap=None,
                   norm=None, logscale=None, vmin=None, vmax=None, aspect=None,
                   **kwargs):
    """
    Make a 2D plot using an xarray method, taking into account branch cuts (X-points).

    Wraps `xarray.plot` methods, so automatically adds labels.

    Parameters
    ----------
    da : xarray.DataArray
        A 2D (x,y) DataArray of data to plot
    method : xarray.plot.*
        An xarray plotting method to use
    ax : Axes, optional
        A matplotlib axes instance to plot to. If None, create a new
        figure and axes, and plot to that
    separatrix : bool, optional
        Add dashed lines showing separatrices
    targets : bool, optional
        Draw solid lines at the target surfaces
    add_limiter_hatching : bool, optional
        Draw hatched areas at the targets
    gridlines : bool, int or slice or dict of bool, int or slice, optional
        If True, draw grid lines on the plot. If an int is passed, it is used as the
        stride when plotting grid lines (to reduce the number on the plot). If a slice is
        passed it is used to select the grid lines to plot.
        If a dict is passed, the 'x' entry (bool, int or slice) is used for the radial
        grid-lines and the 'y' entry for the poloidal grid lines.
    cmap : Matplotlib colormap, optional
        Color map to use for the plot
    norm : matplotlib.colors.Normalize instance, optional
        Normalization to use for the color scale.
        Cannot be set at the same time as 'logscale'
    logscale : bool or float, optional
        If True, default to a logarithmic color scale instead of a linear one.
        If a non-bool type is passed it is treated as a float used to set the linear
        threshold of a symmetric logarithmic scale as
        linthresh=min(abs(vmin),abs(vmax))*logscale, defaults to 1e-5 if True is passed.
        Cannot be set at the same time as 'norm'
    vmin : float, optional
        Minimum value for the color scale
    vmax : float, optional
        Maximum value for the color scale
    aspect : str or float, optional
        Passed to ax.set_aspect(). By default 'equal' is used.
    levels : int or iterable, optional
        Only used by contour or contourf, sets the number of levels (if int) or the level
        values (if iterable)
    **kwargs : optional
        Additional arguments are passed on to method

    Returns
    -------
    artists
        List of the artist instances
    """

    # TODO generalise this
    x = kwargs.pop('x', 'R')
    y = kwargs.pop('y', 'Z')

    if len(da.dims) != 2:
        raise ValueError("da must be 2D (x,y)")

    if ax is None:
        fig, ax = plt.subplots()
    else:
        fig = ax.get_figure()

    if aspect is None:
        aspect = 'equal'
    ax.set_aspect(aspect)

    if vmin is None:
        vmin = da.min().values
    if vmax is None:
        vmax = da.max().values

    # set up 'levels' if needed
    if method is xr.plot.contourf or method is xr.plot.contour:
        levels = kwargs.get('levels', 7)
        if isinstance(levels, np.int):
            levels = np.linspace(vmin, vmax, levels, endpoint=True)
            # put levels back into kwargs
            kwargs['levels'] = levels
        else:
            levels = np.array(list(levels))
            kwargs['levels'] = levels
            vmin = np.min(levels)
            vmax = np.max(levels)

        levels = kwargs.get('levels', 7)
        if isinstance(levels, np.int):
            levels = np.linspace(vmin, vmax, levels, endpoint=True)
            # put levels back into kwargs
            kwargs['levels'] = levels
        else:
            levels = np.array(list(levels))
            kwargs['levels'] = levels
            vmin = np.min(levels)
            vmax = np.max(levels)

    # Need to create a colorscale that covers the range of values in the whole array.
    # Using the add_colorbar argument would create a separate color scale for each
    # separate region, which would not make sense.
    if method is xr.plot.contourf:
        # create colorbar
        norm = _create_norm(logscale, norm, vmin, vmax)
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        # make colorbar have only discrete levels
        # average the levels so that colors in the colorbar represent the intervals
        # between the levels, as contourf colors filled regions between the given levels.
        cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
                'discrete cmap', sm.to_rgba(0.5*(levels[:-1] + levels[1:])),
                len(levels) - 1)
        # re-make sm with new cmap
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        fig.colorbar(sm, ticks=levels, ax=ax)
    elif method is xr.plot.contour:
        # create colormap to be shared by all regions
        norm = matplotlib.colors.Normalize(vmin=levels[0], vmax=levels[-1])
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        cmap = matplotlib.colors.ListedColormap(
                sm.to_rgba(levels), name='discrete cmap')
    else:
        # pass vmin and vmax through kwargs as they are not used for contourf or contour
        # plots
        kwargs['vmin'] = vmin
        kwargs['vmax'] = vmax

        # create colorbar
        norm = _create_norm(logscale, norm, vmin, vmax)
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        cmap = sm.get_cmap()
        fig.colorbar(sm, ax=ax)

    if method is xr.plot.pcolormesh:
        if 'infer_intervals' not in kwargs:
            kwargs['infer_intervals'] = False

    regions = _decompose_regions(da)

    # Plot all regions on same axis
    add_labels = [True] + [False] * (len(regions) - 1)
    artists = [method(region, x=x, y=y, ax=ax, add_colorbar=False, add_labels=add_label,
               cmap=cmap, **kwargs) for region, add_label in zip(regions, add_labels)]

    if method is xr.plot.contour:
        # using extend='neither' guarantees that the ends of the colorbar will be
        # consistent, regardless of whether artists[0] happens to have any values below
        # vmin or above vmax. Unfortunately it does not seem to be possible to combine
        # all the QuadContourSet objects in artists to have this done properly. It would
        # be nicer to always draw triangular ends as if there are always values below
        # vmin and above vmax, but there does not seem to be an option available to force
        # this.
        extend = kwargs.get('extend', 'neither')
        fig.colorbar(artists[0], ax=ax, extend=extend)

    if gridlines is not None:
        # convert gridlines to dict
        if not isinstance(gridlines, dict):
            gridlines = {'x': gridlines, 'y': gridlines}

        for key, value in gridlines.items():
            if value is True:
                gridlines[key] = slice(None)
            elif isinstance(value, int):
                gridlines[key] = slice(0, None, value)
            elif value is not None:
                if not isinstance(value, slice):
                    raise ValueError('Argument passed to gridlines must be bool, int or '
                                     'slice. Got a ' + type(value) + ', ' + str(value))
        R_global = da['R']
        R_global.attrs['metadata'] = da.metadata

        Z_global = da['Z']
        Z_global.attrs['metadata'] = da.metadata

        R_regions = _decompose_regions(da['R'])
        Z_regions = _decompose_regions(da['Z'])

        for R, Z in zip(R_regions, Z_regions):
            if (not da.metadata['bout_xdim'] in R.dims
                    and not da.metadata['bout_ydim'] in R.dims):
                # Small regions around X-point do not have segments in x- or y-directions,
                # so skip
                continue
            if gridlines.get('x') is not None:
                # transpose in case Dataset or DataArray has been transposed away from the usual
                # form
                dim_order = (da.metadata['bout_xdim'], da.metadata['bout_ydim'])
                yarg = {da.metadata['bout_ydim']: gridlines['x']}
                plt.plot(R.isel(**yarg).transpose(*dim_order),
                         Z.isel(**yarg).transpose(*dim_order), color='k', lw=0.1)
            if gridlines.get('y') is not None:
                xarg = {da.metadata['bout_xdim']: gridlines['y']}
                # Need to plot transposed arrays to make gridlines that go in the
                # y-direction
                dim_order = (da.metadata['bout_ydim'], da.metadata['bout_xdim'])
                plt.plot(R.isel(**xarg).transpose(*dim_order),
                         Z.isel(**yarg).transpose(*dim_order), color='k', lw=0.1)

    ax.set_title(da.name)

    if _is_core_only(da):
        separatrix = False
        targets = False

    if separatrix:
        plot_separatrices(da, ax)

    if targets:
        plot_targets(da, ax, hatching=add_limiter_hatching)

    return artists
