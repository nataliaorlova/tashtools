## this file definse functions to manipulate pixel data:
### plot histograms, adjsut contrast, measure SNR, etc

import numpy as np
import scipy.stats
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from skimage import io
from skimage.transform import resize
import tifffile as tiff
import glob

CMAPS = ['Accent', 'Accent_r', 'Blues', 'Blues_r', 'BrBG', 'BrBG_r', 'BuGn', 'BuGn_r', 'BuPu', 'BuPu_r',
                 'CMRmap', 'CMRmap_r', 'Dark2', 'Dark2_r', 'GnBu', 'GnBu_r', 'Greens', 'Greens_r', 'Greys',
                 'Greys_r', 'OrRd', 'OrRd_r', 'Oranges', 'Oranges_r', 'PRGn', 'PRGn_r', 'Paired', 'Paired_r',
                 'Pastel1', 'Pastel1_r', 'Pastel2', 'Pastel2_r', 'PiYG', 'PiYG_r', 'PuBu', 'PuBuGn', 'PuBuGn_r',
                 'PuBu_r', 'PuOr', 'PuOr_r', 'PuRd', 'PuRd_r', 'Purples', 'Purples_r', 'RdBu', 'RdBu_r', 'RdGy',
                 'RdGy_r', 'RdPu', 'RdPu_r', 'RdYlBu', 'RdYlBu_r', 'RdYlGn', 'RdYlGn_r', 'Reds', 'Reds_r', 'Set1',
                 'Set1_r', 'Set2', 'Set2_r', 'Set3', 'Set3_r', 'Spectral', 'Spectral_r', 'Wistia', 'Wistia_r',
                 'YlGn', 'YlGnBu', 'YlGnBu_r', 'YlGn_r', 'YlOrBr', 'YlOrBr_r', 'YlOrRd', 'YlOrRd_r', 'afmhot',
                 'afmhot_r', 'autumn', 'autumn_r', 'binary', 'binary_r', 'bone', 'bone_r', 'brg', 'brg_r', 'bwr',
                 'bwr_r', 'cividis', 'cividis_r', 'cool', 'cool_r', 'coolwarm', 'coolwarm_r', 'copper', 'copper_r',
                 'cubehelix', 'cubehelix_r', 'flag', 'flag_r', 'gist_earth', 'gist_earth_r', 'gist_gray',
                 'gist_gray_r', 'gist_heat', 'gist_heat_r', 'gist_ncar', 'gist_ncar_r', 'gist_rainbow',
                 'gist_rainbow_r', 'gist_stern', 'gist_stern_r', 'gist_yarg', 'gist_yarg_r', 'gnuplot',
                 'gnuplot2', 'gnuplot2_r', 'gnuplot_r', 'gray', 'gray_r', 'hot', 'hot_r', 'hsv', 'hsv_r',
                 'inferno', 'inferno_r', 'jet', 'jet_r', 'magma', 'magma_r', 'nipy_spectral', 'nipy_spectral_r',
                 'ocean', 'ocean_r', 'pink', 'pink_r', 'plasma', 'plasma_r', 'prism', 'prism_r', 'rainbow',
                 'rainbow_r', 'seismic', 'seismic_r', 'spring', 'spring_r', 'summer', 'summer_r', 'tab10',
                 'tab10_r', 'tab20', 'tab20_r', 'tab20b', 'tab20b_r', 'tab20c', 'tab20c_r', 'terrain',
                 'terrain_r', 'twilight', 'twilight_r', 'twilight_shifted', 'twilight_shifted_r', 'viridis',
                 'viridis_r', 'winter', 'winter_r']

def get_pixel_hist2d(x, y, xlabel=None, ylabel=None):
    fig = plt.figure(figsize=(10,10))
    H, xedges, yedges = np.histogram2d(x, y, bins=(30, 30))
    H = H.T
    plt.imshow(H, interpolation='nearest', origin='low',
              extent=[xedges[0], xedges[-1], yedges[0], yedges[-1]], aspect='auto', norm=LogNorm())
    plt.colorbar()

    slope, offset, r_value, p_value, std_err = scipy.stats.linregress(x, y)
    fit_fn = np.poly1d([slope, offset])

    plt.plot(x, fit_fn(x), '--k')
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title('%s    R2=%.2f'%(fit_fn, r_value**2))
    return fig, slope, offset, r_value

def im_plot(path):
    im = io.imread(path)
    fig = plt.imshow(im)
    return fig

def plot_all_colormaps(im):
    for cm in CMAPS:
        plt.figure(figsize=(6, 6))
        plt.imshow(im, cmap = cm)
        plt.title(f'Colormap: {cm}')
        plt.close()
    return

def average_intensity(filepath):
    """
    Inputs the filepath of the lightleak.tiff file and outputs the average pixel value for each frame in the .tiff
    """
    im = tiff.imread(glob.glob(filepath))
    intensity = []
    for frame in range(len(im)):
        x = im[frame].mean(axis=0)
        x = x.mean(axis = 0)
        intensity.append(x)
    return np.array(intensity)

def align_phase(image, do_align = True, offset = None):
    """
    function to aling line phase in an image generated by a bidirectional scanning 
    Inputs:
        image: 2D numpy array representing an image, i.w page of a multipage tiff file
        do_align: bool : if True - perform image alignment, if False - only onput offset value for image
        offset: int : if given, use it to align image, if not - calculate
    Return:
        offset : int : offset calculated or given as input
        image_aligned : 2D numpy array representing phase-aligned image
    """
    
    if not offset : 
        # calculate mean offset in the frame:
        offsets = []
        i=1 
        while i < len(image)-1 : # loop over each pair of lines to calculate pairwise correlation
            offset = image.shape[0]/2 - np.argmax(np.correlate(image[i], image[i+1], mode='same'))
            offsets.append(offset)
            i += 2
        offset = int(np.round(np.mean(offsets)))
    if do_align: 
        if offset > 0:
            # move every line by offset/2
            image_aligned = np.zeros((image.shape[0], int(image.shape[1]+offset)))

            i=0
            while i < len(image)-1: # loop over each pair of lines to insert original data with offset
                image_aligned[i, :-offset] = image[i, :]
                image_aligned[i+1, offset:] = image[i+1]
                i += 2

            image_aligned = image_aligned[:, 1:image_aligned.shape[1]-offset]
            return offset, image_aligned
        else:
            return offset, image
    else:
        return offset

def align_phase_stack(stack):
    """
    fucntion to align phase in images in stack: calculate mean offset for all images, 
        apply same value to all images in stack
    Inputs:
        stack: 3D numpy array representing stack
    Returns:
        stack_aligned: 3D numpy array representing stack, but aligned
    """
    # calculate mean offset in the stack:
    offsets = []
    for page in stack:
        offset = align_phase(page, do_align = False)
        offsets.append(offset)
    mean_offset = int(np.round(np.mean(offsets)))
    max_offset = np.max(offsets)
    # align all images in stack using mean or max offset: 

    if mean_offset !=0:
        offset = mean_offset
    else:
        offset = max_offset

    stack_aligned = np.zeros((stack.shape[0], stack.shape[1], stack.shape[2]-offset))

    for i, page in enumerate(stack):
        _, page_aligned = align_phase(page, offset = offset)
        stack_aligned[i] = page_aligned
    return stack_aligned

def average_n(array, n):
    """averages every N frames of the timeseries
    Input:
        array: numpy 3D array
        n: int: number of rames to average
    Return:
        averaged timeseries
    """
    reshaped_array = array.reshape(n, int(array.shape[0]/n), array.shape[1], array.shape[2])
    avg_array = reshaped_array.mean(axis=0)
    return avg_array

def image_negative_rescale(data):
    """
    mapping image to non-negative range
    data: image as 2D nupmy array
    return: data_out: image with pixel values remapped to a non-negative range
    """
    # rescale image histogram to non negative range
    max_intensity = np.max(data)
    min_intensity = np.min(data)
    data_out = ((data - min_intensity)*2**16/(max_intensity-min_intensity)).astype(np.uint16)
    return data_out

def image_downsample(data, scaling_factor):
    """
    donwssampling image data according ot the sampling factor
    data: 2d numpy array representing the image
    sampling factor: float
    return: downsampled image in a numpy array
    """
    data_scaled_shape = np.asarray(data.shape / scaling_factor, dtype=int)
    data_scaled = (resize(data, data_scaled_shape)*2**16).astype(np.uint16)
    return data_scaled

def offset_to_zero(im):
    imin = im.min()
    im_offset = im-imin
    return im_offset

def image_contrast(image, percentile_max=95, percentile_min=5):
    """Compute contrast of an image.
    Parameters
    ----------
    image : numpy.ndarray, (N, M)
        Image to compute contrast of.
    percentile_max : int
        Percentile at which to compute maximum value of the image
    percentile_min : int
        Percentile at which to compute minimum value of the image
    Returns
    -------
    acutance : float
        Acutance of the image.
    """
    Imax = np.percentile(image, percentile_max)
    Imin = np.percentile(image, percentile_min)
    c = (Imax-Imin)/(Imax+Imin)
    return c

def compute_acutance(image: np.ndarray,
                     cut_y: int = 0,
                     cut_x: int = 0) -> float:
    """Compute the acutance (sharpness) of an image.
    Parameters
    ----------
    image : numpy.ndarray, (N, M)
        Image to compute acutance of.
    cut_y : int
        Number of pixels to cut from the begining and end of the y axis.
    cut_x : int
        Number of pixels to cut from the begining and end of the x axis.
    Returns
    -------
    acutance : float
        Acutance of the image.
    """
    if cut_y <= 0 and cut_x <= 0:
        cut_image = image
    elif cut_y > 0 and cut_x <= 0:
        cut_image = image[cut_y:-cut_y, :]
    elif cut_y <= 0 and cut_x > 0:
        cut_image = image[:, cut_x:-cut_x]
    else:
        cut_image = image[cut_y:-cut_y, cut_x:-cut_x]
    grady, gradx = np.gradient(cut_image)
    return (grady ** 2 + grady ** 2).mean()

def compute_basic_snr(image: np.ndarray):
    """Compute basic SNR of an image as defined by standard deviation / mean of the image
    Parameters
    ----------
    image : numpy.ndarray, (N, M)
        Image to compute SNR of.
    Returns
    -------
    basic_snr : float
        Basic SNR of an image.
    """
    basic_snr = np.std(image.flatten())/np.mean(image.flatten())
    return basic_snr