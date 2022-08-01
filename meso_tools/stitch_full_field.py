# This file has the code needed to process large FOV stack:
# 1. Asses all following:
#   a) stack is of correct type
#   b) only channel 1 saving is enabled
#   c) all rois are in non-discrete plane mode
#   d) all rois have only one scanfield
#   d) all rois are of the same pixel size and degree size (scaling would be too much work, plus we don't want to create a mess with resolution)
# 2. Get all above values for the stack (num of planes, etc)
# 3. Asses that tiff size is correct
# 4. If multiple repeats of the stack (volumes) - average them out before stitching
# 7. Stitching:
#       For nth z in z array:
#           Load nth page of tiff
#           For each roi in rois:
#               Get roi’s pixel size, and location
#               Get portion of the tiff to insert, inset to location in destination file
# 8. split and avergae surface images 
# 9. insert surface averages into stitched tiff
#       downsample to match full field file resolution

#       figure out insert coordinates
#           normalization w regards to full field is problematic 

from matplotlib import path
from meso_tools.io_utils import read_si_metadata as get_meta
from meso_tools.io_utils import read_tiff, write_tiff
import numpy as np
from skimage.transform import  resize

GAP = 24

def read_full_field_meta(metadata):
    """
    reading of the relevant metadata fields
    return: dict
    """
    md_general = metadata[0]  
    meta_dict = {}
    
    # quantifying properties:
    meta_dict['num_slices'] = md_general['SI.hStackManager.actualNumSlices']
    meta_dict['num_volumes'] = md_general['SI.hStackManager.actualNumVolumes']
    meta_dict['z_step'] = md_general['SI.hStackManager.actualStackZStepSize']
    meta_dict['all_zs'] = np.asarray(md_general['SI.hStackManager.zsAllActuators'])[:,1]
    meta_dict['frames_per_slice'] = md_general['SI.hStackManager.framesPerSlice']
    
    #flag properties:
    meta_dict['channel_save'] = md_general['SI.hChannels.channelSave']
    meta_dict['stack_type'] = md_general['SI.hStackManager.stackDefinition']

    #metadata related to specific rois/scanfields
    meta_dict['rois'] = metadata[1]['RoiGroups']['imagingRoiGroup']['rois']
    return meta_dict

def check_meta(meta_dict):
    """
    assertions to check if the stack is of correct type and skimming off metadata
    1. Unifrom, non-centered
    2. only channel 1 is set to be saved
    3. all ROIs are in non-discrete mode 
    """
    assert isinstance(meta_dict['channel_save'], int), f"More than 1 channel is set ot be saved when data acquired, unable to split"
    assert meta_dict['stack_type'] == 'uniform', f"stack is of wrong type, unable to split"

    # check that all ROIs are in discrete plane mode
    for i,roi in enumerate(meta_dict['rois']):
        assert roi['discretePlaneMode'] == 0, f"ROI {i} is not in discrete plane mode - unable to split"
        assert isinstance(roi['scanfields'], dict), f"ROI {i} has more than one scnafield - unable to split"

    #checking that all rois are of the same size:
    pix_res = [roi['scanfields']['pixelResolutionXY'] for roi in  meta_dict['rois']]
    assert all(elem == pix_res[0] for elem in pix_res), f'ROIs are not of the same shape, unable to stitch'

    degree_size = [roi['scanfields']['sizeXY'] for roi in  meta_dict['rois']]
    assert all(elem == degree_size[0] for elem in degree_size), f'ROIs are not of the same size, unable to stitch'
    # take pixel resolution of hte first ROI since we checked that they all are of the same rezolution
    meta_dict['pixel_to_degree'] = np.array(pix_res[0])/np.array(degree_size[0]) 

    return meta_dict

def check_tiff(tiff_array, meta_dict):
    """
    calculate what tiff size should be, check if it's correct, calculate output tiff shape
    """
    # get tiff size
    tiff_shape = np.shape(tiff_array)
    rois = meta_dict['rois']
    num_slices = meta_dict['num_slices']
    num_repeats = meta_dict['num_volumes']
    # calculate what tiff shape should be:
    pix_res = rois[0]['scanfields']['pixelResolutionXY']
    output_tiff_shape =  [pix_res[0]*len(rois), pix_res[1]]
    expected_tiff_shape = [num_slices*num_repeats, pix_res[1]*len(rois)+(GAP*(len(rois)-1)), pix_res[0]]
    tiff_shape = np.shape(tiff_array)

    assert expected_tiff_shape == list(tiff_shape), f"Input tiff shape is unexpected"

    return output_tiff_shape

def average_tiff(tiff_array, meta):
    """
    average input tiff over all slices and number of stack repeats
    return : a single page tiff (2D np.array)
    """
    slices = meta['num_volumes'] # number of z slices
    # let's average eover repeats and slices
    # resahpe tp get array of [slices, repeats, y_pix_size, x_pix_size]
    x = tiff_array.reshape(tiff_array.shape[0] // slices, slices, tiff_array.shape[1], tiff_array.shape[2]) 
    # average over slices:
    y = x.mean(axis = 0) 
    # average over repeats:
    repeats = meta['num_volumes'] # this is number of repeats we want to average
    if repeats > 1 : 
        averaged_tiff = y.mean(axis=0)
    else:
        averaged_tiff = y
    return averaged_tiff

def stitch_tiff(averaged_tiff, meta_dict, output_tiff_shape):
    """
    actually stitch the file into a full FOV image
    returns: stitched image, 2D mumpy array
    """

    rois = meta_dict['rois']

    output_tiff_shape = [output_tiff_shape[1],output_tiff_shape[0]]

    stitched_tiff = np.empty(output_tiff_shape)

    pix_to_deg_x = rois[0]['scanfields']['pixelResolutionXY'][0]/rois[0]['scanfields']['sizeXY'][0]
    pix_to_deg_y = rois[0]['scanfields']['pixelResolutionXY'][1]/rois[0]['scanfields']['sizeXY'][1]

    roi_centers = np.array([roi['scanfields']['centerXY'] for roi in  rois]) # [x,y] array of ROI centers in degrees
    roi_sizes = np.array([roi['scanfields']['sizeXY'] for roi in  rois]) # [x, y] array of ROI sizes in degrees

    # calculate top right corner, degrees
    insert_top_right = roi_centers - roi_sizes/2
    insert_bottom_left = roi_centers + roi_sizes/2

    #normalize top right corner coords, degrees
    roi_x_min = np.min([i[0] for i in insert_top_right])
    roi_y_min = np.min([i[1] for i in insert_top_right])
    insert_top_right -= [roi_x_min, roi_y_min]
    meta_dict['min_x'] = roi_x_min
    meta_dict['min_y'] = roi_y_min
    
    #normalize bottom left corner coords, degrees
    insert_bottom_left -= [roi_x_min, roi_y_min]

    # convert insert coordinates to pixels
    insert_top_right *= [pix_to_deg_x, pix_to_deg_y]
    insert_top_right = insert_top_right.round(0)
    insert_top_right = insert_top_right.astype(np.int16)
    insert_top_right[:, [1, 0]] = insert_top_right[:, [0, 1]]

    insert_bottom_left *= [pix_to_deg_x, pix_to_deg_y]
    insert_bottom_left = insert_bottom_left.round(0)
    insert_bottom_left = insert_bottom_left.astype(np.int16)
    insert_bottom_left[:, [1, 0]] = insert_bottom_left[:, [0, 1]]

    # convert sizes to pixels:
    roi_sizes *= np.array([pix_to_deg_x, pix_to_deg_y])
    roi_sizes = roi_sizes.astype(int)

    cut_top_right = np.array([[i*(roi_sizes[i][1] + GAP), 0] for i, roi in enumerate(rois)])
    cut_bottom_left = np.array([[(i+1)*(roi_sizes[i][1]) + i*GAP, roi_sizes[i][0]] for i, roi in enumerate(rois)])

    for i, _ in enumerate(rois):
        averaged_tiff = im_negative_rescale(averaged_tiff)
        image_to_insert = averaged_tiff[cut_top_right[i][0]:cut_bottom_left[i][0], cut_top_right[i][1]:cut_bottom_left[i][1]]
        stitched_tiff[insert_top_right[i][0]:insert_bottom_left[i][0], insert_top_right[i][1]:insert_bottom_left[i][1]] = image_to_insert

    return stitched_tiff, meta_dict

def split_surface(path_to_surface):

    surface_array = read_tiff(path_to_surface)
    surface_meta = get_meta(path_to_surface)
    surface_meta_dict = {}
    surface_meta_dict['rois'] = surface_meta[1]['RoiGroups']['imagingRoiGroup']['rois']
    surface_meta_dict['num_repeats'] = surface_meta[0]['SI.hStackManager.actualNumVolumes']
    surface_meta_dict['num_rois'] = len(surface_meta_dict['rois'])

    # averaging over number of repeats: 
    surface_averaged = np.average(surface_array.reshape(surface_meta_dict['num_repeats'], -1, surface_array.shape[1], surface_array.shape[2]), axis=0)

    for i in range(len(surface_meta_dict['rois'])):
        surface_meta_dict['rois'][i]['array'] = surface_averaged[i, :,:]

    return surface_meta_dict, surface_averaged

def im_negative_rescale(data):
    """
    mapping image to non-negative range
    data: inmage as 2D nupmy array
    return: data_out: remapped image
    """
    # rescale image histogram to non negative range
    max_intensity = np.max(data)
    min_intensity = np.min(data)
    data_out = ((data - min_intensity)*2**16/(max_intensity-min_intensity)).astype(np.uint16)
    return data_out

def data_downsample(data, scaling_factor):
    """
    donwssampling image data according ot the sampling factor
    data: 2d numpy array representing the image
    sampling factor: float
    return: downsampled image in a numpy array
    """
    data_scaled_shape = np.asarray(data.shape / scaling_factor, dtype=int)
    data_scaled = (resize(data, data_scaled_shape)*2**16).astype(np.uint16)
    return data_scaled


def insert_surface_to_ff(ff_stitched_tiff, ff_meta_dict, split_surface_meta):

    # get pixel to degrees for full field data
    pixel_resolution_ff = ff_meta_dict['pixel_to_degree']
    right_corner_ff = np.array([ff_meta_dict['min_y'], ff_meta_dict['min_x']])

    # get pixel resolution and check that resolution of all rois in surface is the same
    pix_res = [roi['scanfields']['pixelResolutionXY'] for roi in  split_surface_meta['rois']]
    assert all(elem == pix_res[0] for elem in pix_res), f'ROIs are not of the same shape, unable to stitch'
    pix_res_surface = np.array(pix_res[0])

    # get degree size and check that resolution of all rois in surface is the same
    degree_size = [roi['scanfields']['sizeXY'] for roi in  split_surface_meta['rois']]
    assert all(elem == degree_size[0] for elem in degree_size), f'ROIs are not of the same shape, unable to stitch'
    degree_size_surface = np.array(degree_size[0])

    # finally, pixel to degree for surface data
    pixel_resolution_surf = pix_res_surface / degree_size_surface

    # bring two piece of data tot eh same pix/degree (usually this means downsampling surafce tiff arrays)
    # calculate scaling factor
    convert_factor = pixel_resolution_surf/pixel_resolution_ff
    # downsampling 
    for i, roi in enumerate(split_surface_meta["rois"]):
        a = roi['array']
        b = im_negative_rescale(a)
        c = data_downsample(b, convert_factor)
        roi['downsampled_array'] = c
    
    for roi in split_surface_meta["rois"]:
        scanfield = roi['scanfields']
        roi_center = np.array(scanfield['centerXY']) # get center
        roi_size = np.array(scanfield['sizeXY']) # get size
        # convert to pixels
        roi_center *= pixel_resolution_ff
        roi_size *= pixel_resolution_ff
        # round down
        roi_size = np.floor(roi_size)
        roi_center = np.floor(roi_center)
        # caculate paste coordinates
        top_right = roi_center - roi_size/2 
        bottom_left = roi_center + roi_size/2

        # normalize to right top corner    
        top_right -= (right_corner_ff * pixel_resolution_ff)
        bottom_left -= (right_corner_ff * pixel_resolution_ff)

        # cast as int
        top_right = top_right.astype(np.int16)
        bottom_left = bottom_left.astype(np.int16)

        #insert into full field image:
        ff_stitched_tiff[top_right[1]:bottom_left[1], top_right[0]:bottom_left[0]] = roi['downsampled_array']

    return ff_stitched_tiff


if __name__ == "__main__":

    GAP = 24

    path_to_tiff = "/Users/nataliaorlova/Code/data/incoming/1180346813_fullfield.tiff"

    tiff_array = read_tiff(path_to_tiff)

    meta = get_meta(path_to_tiff)

    ff_meta_dict = read_full_field_meta(meta)

    ff_meta_dict = check_meta(ff_meta_dict)

    check_tiff(tiff_array, ff_meta_dict)

    output_tiff_shape = check_tiff(tiff_array, ff_meta_dict)

    ff_averaged_tiff = average_tiff(tiff_array, ff_meta_dict)

    ff_stitched_tiff, ff_meta_dict = stitch_tiff(ff_averaged_tiff, ff_meta_dict, output_tiff_shape)
    surface_path = "/Users/nataliaorlova/Code/data/incoming/1180346813_averaged_surface.tiff"

    split_surface_meta, surface_averaged = split_surface(surface_path)

    write_path = "/Users/nataliaorlova/Code/data/incoming/1180346813_fullfield_stitched.tiff"
    write_tiff(write_path, ff_stitched_tiff)

# ToDo
# how to pass the filepath to this file without using argparser?