from pprint import pformat as prettyformat
from functools import partial

import xarray as xr
from xarray import register_dataarray_accessor

from .plotting.animate import animate_poloidal, animate_pcolormesh, animate_line
from .plotting import plotfuncs
from .plotting.utils import _create_norm


@register_dataarray_accessor('bout')
class BoutDataArrayAccessor:
    """
    Contains BOUT-specific methods to use on BOUT++ dataarrays opened by
    selecting a variable from a BOUT++ dataset.

    These BOUT-specific methods and attributes are accessed via the bout
    accessor, e.g. `da.bout.options` returns a `BoutOptionsFile` instance.
    """

    def __init__(self, da):
        self.data = da
        self.metadata = da.attrs.get('metadata')  # None if just grid file
        self.options = da.attrs.get('options')  # None if no inp file

    def __str__(self):
        """
        String representation of the BoutDataArray.

        Accessed by print(da.bout)
        """

        styled = partial(prettyformat, indent=4, compact=True)
        text = "<xbout.BoutDataset>\n" + \
               "Contains:\n{}\n".format(str(self.data)) + \
               "Metadata:\n{}\n".format(styled(self.metadata))
        if self.options:
            text += "Options:\n{}".format(styled(self.options))
        return text

    def animate2D(self, animate_over='t', x=None, y=None, animate=True, fps=10,
                  save_as=None, ax=None, poloidal_plot=False, logscale=None, **kwargs):
        """
        Plots a color plot which is animated with time over the specified
        coordinate.

        Currently only supports 2D+1 data, which it plots with animatplot's
        wrapping of matplotlib's pcolormesh.

        Parameters
        ----------
        animate_over : str, optional
            Dimension over which to animate
        x : str, optional
            Dimension to use on the x axis, default is None - then use the first spatial
            dimension of the data
        y : str, optional
            Dimension to use on the y axis, default is None - then use the second spatial
            dimension of the data
        sep_pos : int, optional
            Radial position at which to plot the separatrix
        fps : int, optional
            Frames per second of resulting gif
        save_as : str, optional
            Filename to give to the resulting gif
        ax : matplotlib.pyplot.axes object, optional
            Axis on which to plot the gif
        poloidal_plot : bool, optional
            Use animate_poloidal to make a plot in R-Z coordinates (input field must be
            (t,x,y))
        logscale : bool or float, optional
            If True, default to a logarithmic color scale instead of a linear one.
            If a non-bool type is passed it is treated as a float used to set the linear
            threshold of a symmetric logarithmic scale as
            linthresh=min(abs(vmin),abs(vmax))*logscale, defaults to 1e-5 if True is
            passed.
        kwargs : dict, optional
            Additional keyword arguments are passed on to the plotting function
            (e.g. imshow for 2D plots).
        """

        data = self.data
        variable = data.name
        n_dims = len(data.dims)

        if n_dims == 3:
            vmin = kwargs['vmin'] if 'vmin' in kwargs else data.min().values
            vmax = kwargs['vmax'] if 'vmax' in kwargs else data.max().values
            kwargs['norm'] = _create_norm(logscale, kwargs.get('norm', None), vmin, vmax)

            if poloidal_plot:
                print("{} data passed has {} dimensions - making poloidal plot with "
                      "animate_poloidal()".format(variable, str(n_dims)))
                if x is not None:
                    kwargs['x'] = x
                if y is not None:
                    kwargs['y'] = y
                poloidal_blocks = animate_poloidal(data, animate_over=animate_over,
                                                   animate=animate, fps=fps,
                                                   save_as=save_as, ax=ax, **kwargs)
                return poloidal_blocks
            else:
                print("{} data passed has {} dimensions - will use "
                      "animatplot.blocks.Pcolormesh()".format(variable, str(n_dims)))
                pcolormesh_block = animate_pcolormesh(data=data,
                                                      animate_over=animate_over, x=x,
                                                      y=y, animate=animate, fps=fps,
                                                      save_as=save_as, ax=ax, **kwargs)
                return pcolormesh_block
        else:
            raise ValueError(
                "Data passed has an unsupported number of dimensions "
                "({})".format(str(n_dims)))

    def animate1D(self, animate_over='t', x='x', y='y', animate=True,
                  fps=10, save_as=None, sep_pos=None, ax=None, **kwargs):
        data = self.data
        variable = data.name
        n_dims = len(data.dims)

        if n_dims == 2:
            print("{} data passed has {} dimensions - will use "
                  "animatplot.blocks.Line()".format(variable, str(n_dims)))
            line_block = animate_line(data=data, animate_over=animate_over,
                                      sep_pos=sep_pos, animate=animate, fps=fps,
                                      save_as=save_as, ax=ax, **kwargs)
            return line_block

    # BOUT-specific plotting functionality: methods that plot on a poloidal (R-Z) plane
    def contour(self, ax=None, **kwargs):
        return plotfuncs.plot2d_wrapper(self.data, xr.plot.contour, ax=ax, **kwargs)

    def contourf(self, ax=None, **kwargs):
        return plotfuncs.plot2d_wrapper(self.data, xr.plot.contourf, ax=ax, **kwargs)

    def pcolormesh(self, ax=None, **kwargs):
        return plotfuncs.plot2d_wrapper(self.data, xr.plot.pcolormesh, ax=ax, **kwargs)

    def regions(self, ax=None, **kwargs):
        return plotfuncs.regions(self.data, ax=ax, **kwargs)
