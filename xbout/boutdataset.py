from pathlib import Path
from pprint import pformat as prettyformat
from functools import partial

import animatplot as amp
from matplotlib import pyplot as plt
import numpy as np
from xarray import register_dataset_accessor, \
    save_mfdataset, set_options, merge
from dask.diagnostics import ProgressBar

from .load import _auto_open_mfboutdataset
from .plotting.animate import animate_imshow, animate_line


# This code should run whenever any function from this module is imported
# Set all attrs to survive all mathematical operations
# (see https://github.com/pydata/xarray/pull/2482)
try:
    set_options(keep_attrs=True)
except ValueError:
    raise ImportError("For dataset attributes to be permanent you need to be "
                      "using the development version of xarray - found at "
                      "https://github.com/pydata/xarray/")
try:
    set_options(file_cache_maxsize=256)
except ValueError:
    raise ImportError("For open and closing of netCDF files correctly you need"
                      " to be using the development version of xarray - found"
                      " at https://github.com/pydata/xarray/")

# TODO somehow check that we have access to the latest version of auto_combine


def open_boutdataset(datapath='./BOUT.dmp.*.nc',
                     inputfilepath=None, gridfilepath=None, chunks={},
                     run_name=None, info=True):
    """
    Load a dataset from a set of BOUT output files, including the input options file.

    Parameters
    ----------
    datapath : str, optional
    prefix : str, optional
    slices : slice object, optional
    chunks : dict, optional
    inputfilepath : str, optional
    gridfilepath : str, optional
    run_name : str, optional
    info : bool, optional

    Returns
    -------
    ds : xarray.Dataset
    """

    # TODO handle possibility that we are loading a previously saved (and trimmed) dataset

    # Gather pointers to all numerical data from BOUT++ output files
    ds, metadata = _auto_open_mfboutdataset(datapath=datapath, chunks=chunks)
    ds = _set_attrs_on_all_vars(ds, 'metadata', metadata)

    if inputfilepath:
        # Use Ben's options class to store all input file options
        with open(inputfilepath, 'r') as f:
            config_string = "[dummysection]\n" + f.read()
        options = configparser.ConfigParser()
        options.read_string(config_string)
    else:
        options = None
    ds = _set_attrs_on_all_vars(ds, 'options', options)

    # TODO This is where you would load the grid file as a separate object
    # (Ideally using xgcm but could also just store the grid.nc file as another dataset)

    # TODO read and store git commit hashes from output files

    if run_name:
        ds.name = run_name

    if info is 'terse':
        print("Read in dataset from {}".format(str(Path(datapath))))
    elif info:
        print("Read in:\n{}".format(ds.bout))

    return ds


def _set_attrs_on_all_vars(ds, key, attr_data):
    ds.attrs[key] = attr_data
    for da in ds.values():
        da.attrs[key] = attr_data
    return ds


@register_dataset_accessor('bout')
class BoutDatasetAccessor:
    """
    Contains BOUT-specific methods to use on BOUT++ datasets opened using
    `open_boutdataset()`.

    These BOUT-specific methods and attributes are accessed via the bout
    accessor, e.g. `ds.bout.options` returns a `BoutOptionsFile` instance.
    """

    def __init__(self, ds):
        self.data = ds
        self.metadata = ds.attrs.get('metadata')  # None if just grid file
        self.options = ds.attrs.get('options')  # None if no inp file
        self.grid = ds.attrs.get('grid')  # None if no grid file

    def __str__(self):
        """
        String representation of the BoutDataset.

        Accessed by print(ds.bout)
        """

        styled = partial(prettyformat, indent=4, compact=True)
        text = "<xbout.BoutDataset>\n" + \
               "Contains:\n{}\n".format(str(self.data)) + \
               "Metadata:\n{}\n".format(styled(self.metadata))
        if self.options:
            text += "Options:\n{}".format(styled(self.options))
        if self.grid:
            text += "Grid:\n{}".format(styled(self.grid))
        return text

    #def __repr__(self):
    #    return 'boutdata.BoutDataset(', {}, ',', {}, ')'.format(self.datapath,
    #  self.prefix)

    def save(self, savepath='./boutdata.nc', filetype='NETCDF4',
             variables=None, save_dtype=None, separate_vars=False):
        """
        Save data variables to a netCDF file.

        Parameters
        ----------
        savepath : str, optional
        filetype : str, optional
        variables : list of str, optional
            Variables from the dataset to save. Default is to save all of them.
        separate_vars: bool, optional
            If this is true then every variable which depends on time will be saved into a different output file.
            The files are labelled by the name of the variable. Variables which don't depend on time will be present in
            every output file.
        """

        if variables is None:
            # Save all variables
            to_save = self.data
        else:
            to_save = self.data[variables]

        if savepath is './boutdata.nc':
            print("Will save data into the current working directory, named as"
                  " boutdata_[var].nc")
        if savepath is None:
            raise ValueError('Must provide a path to which to save the data.')

        if save_dtype is not None:
            to_save = to_save.astype(save_dtype)

        # TODO How should I store other data? In the attributes dict?
        # TODO Convert Ben's options class to a (flattened) nested dictionary then store it in ds.attrs?
        # TODO Save grid data too
        if self.options is None:
            to_save.attrs = {}
        else:
            # Store the metadata as individual attributes because netCDF can't
            # handle storing arbitrary objects in attrs
            for key in to_save.attrs['metadata']:
                to_save[key] = self.metadata[key]
            to_save.attrs['metadata'] = self.metadata

        if separate_vars:
            # Save each time-dependent variable to a different netCDF file

            # Determine which variables are time-dependent
            time_dependent_vars, time_independent_vars = \
                _find_time_dependent_vars(to_save)

            print("Will save the variables {} separately"
                  .format(str(time_dependent_vars)))

            # Save each one to separate file
            for var in time_dependent_vars:
                # Group variables so that there is only one time-dependent
                # variable saved in each file
                time_independent_data = [to_save[time_ind_var] for
                                         time_ind_var in time_independent_vars]
                single_var_ds = merge([to_save[var], *time_independent_data])

                # Include the name of the variable in the name of the saved
                # file
                path = Path(savepath)
                var_savepath = str(path.parent / path.stem) + '_' \
                               + str(var) + path.suffix
                print('Saving ' + var + ' data...')
                with ProgressBar():
                    single_var_ds.to_netcdf(path=str(var_savepath),
                                            format=filetype, compute=True)
        else:
            # Save data to a single file
            print('Saving data...')
            with ProgressBar():
                to_save.to_netcdf(path=savepath, format=filetype, compute=True)

        return

    def to_restart(self, savepath='.', nxpe=None, nype=None,
                   original_splitting=False):
        """
        Write out final timestep as a set of netCDF BOUT.restart files.

        If processor decomposition is not specified then data will be saved
        using the decomposition it had when loaded.

        Parameters
        ----------
        savepath : str
        nxpe : int
        nype : int
        """

        # Set processor decomposition if not given
        if original_splitting:
            if any([nxpe, nype]):
                raise ValueError('Inconsistent choices for domain '
                                 'decomposition.')
            else:
                nxpe, nype = self.metadata['NXPE'], self.metadata['NYPE']

        # Is this even possible without saving the ghost cells?
        # Can they be recreated?
        restart_datasets, paths = _split_into_restarts(self.data, savepath,
                                                       nxpe, nype)
        with ProgressBar():
            save_mfdataset(restart_datasets, paths, compute=True)
        return

    def animate_list(self, variables, animate_over='t', save_as=None, show=False, fps=10,
                     nrows=None, ncols=None, **kwargs):
        nvars = len(variables)

        if nrows is None and ncols is None:
            ncols = int(np.ceil(np.sqrt(nvars)))
            nrows = int(np.ceil(nvars/ncols))
        elif nrows is None:
            nrows = int(np.ceil(nvars/ncols))
        elif ncols is None:
            ncols = int(np.ceil(nvars/nrows))
        else:
            if nrows*ncols < nvars:
                raise ValueError('Not enough rows*columns to fit all variables')

        fig, axes = plt.subplots(nrows, ncols, squeeze=False)

        blocks = []
        for v, ax in zip(variables, axes.flatten()):
            data = v.bout.data
            ndims = len(data.dims)
            ax.set_title(data.name)

            if ndims == 2:
                blocks.append(animate_line(data=data, ax=ax, animate_over=animate_over,
                              animate=False, **kwargs))
            elif ndims == 3:
                blocks.append(animate_imshow(data=data, ax=ax, animate_over=animate_over,
                              animate=False, **kwargs))
            else:
                raise ValueError("Unsupported number of dimensions "
                                 + str(ndims) + ". Dims are " + str(v.dims))

        timeline = amp.Timeline(np.arange(variables[0].sizes[animate_over]), fps=fps)
        anim = amp.Animation(blocks, timeline)
        anim.controls(timeline_slider_args={'text': animate_over})

        if save_as is not None:
            anim.save(save_as + '.gif', writer='imagemagick')

        if show:
            plt.show()

        return anim


def _find_time_dependent_vars(data):
    evolving_vars = set(var for var in data.data_vars if 't' in data[var].dims)
    time_independent_vars = set(data.data_vars) - set(evolving_vars)
    return list(evolving_vars), list(time_independent_vars)
