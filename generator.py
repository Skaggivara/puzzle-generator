#!/usr/bin/env python

from PIL import Image

import json
import fileinput
import os
import sys
import random
from optparse import OptionParser
from subprocess import call, check_call, CalledProcessError


MASK_SIZE           = 200.0
IMG_AREA_SIZE       = 139.0

RATIO               = MASK_SIZE/IMG_AREA_SIZE
ATLAS_SIZES         = [1024, 2048, 4096]
PADDING             = 2

PIECE_SIZE          = 100

TEXTURE_TOOL_PATH   = os.path.join("/Applications/Xcode.app/Contents/Developer/Platforms/iPhoneOS.platform/Developer/usr/bin/","texturetool")

TMP_FOLDER          = "tmp"
MASK_FOLDER         = "mask"
OUTPUT_FOLDER       = "output"

def create_pieces(options=None):
    
    if os.path.exists(os.path.join(os.getcwd(), MASK_FOLDER)) is not True:
        print "You need to be in the folder with a 'mask' folder"
        sys.exit(1)
    
    if _imagemagick_installed() is not True:
        print "You need imagemagick installed to run this program"
        sys.exit(1)
    
    if _texturetools_installed() is not True:
        print "If you want to compress textures you need texturetools installed at '%s'" % TEXTURE_TOOL_PATH
    
    PIECE_SIZE = options.size
    PADDING = options.padding
    
    # see that we have the nessesary folders
    _silent_mkdir(os.path.join(os.getcwd(), TMP_FOLDER))
    _silent_mkdir(os.path.join(os.getcwd(), OUTPUT_FOLDER))
    
    # some file basics..
    image_file = options.filename
    directory = os.path.dirname(image_file)
    basename = os.path.splitext(os.path.basename(image_file))[0]
    
    # check size of input image
    img = Image.open(image_file)
    
    # get the image's width and height in pixels
    img_w, img_h = img.size
    
    w_remainder = img_w % PIECE_SIZE
    h_remainder = img_h % PIECE_SIZE
    
    n_width = img_w - w_remainder
    n_height = img_h - h_remainder
    
    # does it need resizing?
    fixed_file = image_file
    if w_remainder != 0 or h_remainder != 0:
    
        print "optimizing image size..."
        
        fixed_file = os.path.join(os.getcwd(), TMP_FOLDER, "size_fixed.png")
        
        # cropping to fitting size
        call(["convert", image_file, "-gravity", "Center", "-crop","%dx%d+0+0" % (n_width, n_height), "+repage", fixed_file])
    
    rows = n_height / PIECE_SIZE
    columns = n_width / PIECE_SIZE
    
    mask_piece_size = int((PIECE_SIZE * RATIO)+.5)
    
    
    # add border to make piece fitting easier
    border_size = int((mask_piece_size - PIECE_SIZE) * .5)
    
    bordered_file = os.path.join(os.getcwd(), TMP_FOLDER, "bordered.png")
    
    print "adding border..."
    call(["convert", fixed_file, "-matte", "-bordercolor", "none", "-border", "%d" % border_size, bordered_file])
    
    # generate playing field
    pieces_info = generate_pieces(rows,columns)

    # create pieces
    print "creating pieces, this could take a while..."
    print_pieces(bordered_file, mask_piece_size, PIECE_SIZE, pieces_info)
    
    # fit pieces onto atlas
    atlases = []
    
    atlases_required = atlases_needed(mask_piece_size + (PADDING*2), len(pieces_info))
    
    print "creating atlases..."
    for i in range(len(atlases_required)):
        
        pieces_subset = pieces_info[0:atlases_required[i]["pieces"]]
        
        atlases.append(print_to_atlas("%s_%d" % (basename, i), atlases_required[i]['size'], mask_piece_size, pieces_subset))
        
        pieces_info = pieces_info[atlases_required[i]["pieces"]:len(pieces_info)]
        
    # print array of atlases json data
    data_file = open(os.path.join(os.getcwd(), OUTPUT_FOLDER, "%s_atlas.json" % basename), 'w')
    data_file.write(json.dumps(atlases))
    data_file.close()
    
    print "all done!"
    

def atlases_needed(piece_size, num_pieces):
    atlases = []
    while(num_pieces>0):
        target_atlas_size = get_atlas_fit(piece_size, num_pieces)
        if target_atlas_size is not None:
            atlases.append({"size":target_atlas_size, "pieces":num_pieces})
            num_pieces = 0
        else:
            in_atlas = get_atlas_max(ATLAS_SIZES[-1], piece_size)
            atlases.append({"size":ATLAS_SIZES[-1], "pieces":in_atlas})
            num_pieces -= in_atlas
    
    return atlases

# DONE!    
def print_pieces(input, piece_size, offset, pieces):
    
    for i in range(len(pieces)):
        
        x = pieces[i]["offset"][0]
        y = pieces[i]["offset"][1]
        
        mask = os.path.join(os.getcwd(), TMP_FOLDER, "mask.png")
        
        call(["convert", pieces[i]["mask"], "-adaptive-resize", "%dx%d" % (piece_size,piece_size), mask])
        call(["convert", input, mask, "-geometry", "+%d+%d" % (x * offset, y * offset), "-alpha", "Off", "-compose", "CopyOpacity", "-composite", "-crop","%dx%d+%d+%d" % (piece_size, piece_size, x * offset, y * offset), os.path.join(os.getcwd(), TMP_FOLDER, "x%d_y%d.png" % (x, y))])
    

# DONE
def print_to_atlas(name, size, piece_size, pieces):
    
    atlas_info = {
        "size": size,
        "unit": piece_size,
        "padding": PADDING,
        "filename": "%s_atlas_%sx%s.png" % (name, size, size), 
        "pieces": []
    }
    
    canvas = os.path.join(os.getcwd(), TMP_FOLDER, "atlas_temp.png")
    # make texture atlas
    call(["convert", "-size","%dx%d" % (size, size), "canvas:khaki", "-alpha", "transparent", canvas])
    
    atlas_command = ["convert", canvas]
    
    per_row = size / (piece_size + (PADDING * 2))
    
    row = 0
    col = 0
    for i in range(len(pieces)):
        if col == per_row:
            col = 0
            row += 1
        x = pieces[i]["offset"][0]
        y = pieces[i]["offset"][1]
        
        piece_w_h = piece_size + (PADDING * 2)
        
        real_x = (col * piece_w_h)+PADDING
        real_y = (row * piece_w_h)+PADDING
        
        tile = os.path.join(os.getcwd(), TMP_FOLDER, "x%d_y%d.png" % (x, y))
        
        atlas_command += ["-draw", "image Over %d,%d %d,%d '%s'" % (real_x, real_y, piece_size, piece_size, tile)]
        atlas_info["pieces"].append({"id":[x,y], "x":[((col*piece_w_h)+PADDING)/float(size),(((col+1)*piece_w_h)+PADDING)/float(size)], "y":[((row*piece_w_h)+PADDING)/float(size),(((row+1)*piece_w_h)+PADDING)/float(size)]})
        col += 1
    
    result = os.path.join(os.getcwd(), OUTPUT_FOLDER, "%s_atlas_%sx%s.png" % (name, size, size))
    
    atlas_command.append(result)
    
    call(atlas_command)
    
    return atlas_info    

# DONE! how many pieces in this size atlas
def get_atlas_max(size, piece_size):
    per_row = size / piece_size
    return per_row * per_row
    
# DONE! whats the smallest fit for these pieces
def get_atlas_fit(piece_size, num_pieces):
    for i in range(len(ATLAS_SIZES)):
        per_atlas = get_atlas_max(ATLAS_SIZES[i], piece_size)
        if per_atlas >= num_pieces:
            return ATLAS_SIZES[i]
    return None

# DONE! generate a playing field
def generate_pieces(rows, columns):
    
    pieces = []
    
    for row in range(rows):
        for column in range(columns):
            
            piece = {
                "mask": "",
                "corners": [0,0,0,0],
                "offset": [column, row]
            }
            
            piece_type = "middle"
            if row == 0:
                piece_type = "top"
                
            if row == (row-1):
                piece_type = "bottom"
            
            if column == 0:
                piece_type = "left"
                
            if column == (columns-1):
                piece_type = "right"
                
            if row == 0 and column == 0:
                piece_type = "left_top"
            
            if row == 0 and column == (columns-1):
                piece_type = "right_top"
            
            if row == (rows-1) and column == 0:
                piece_type = "left_bottom"
            
            if row == (rows-1) and column == (columns-1):
                piece_type = "right_bottom"
            
            if piece_type == "left_top":
                piece["corners"] = [0, random.randint(0,1), random.randint(0,1), 0]
            
            if piece_type == "top":
                last_one = pieces[len(pieces)-1]
                piece["corners"] = [0, random.randint(0,1), random.randint(0,1), 1 - last_one["corners"][1]]
            
            if piece_type == "right_top":
                last_one = pieces[len(pieces)-1]
                piece["corners"] = [0, 0, random.randint(0,1), 1 - last_one["corners"][1] ]
            
            if piece_type == "left":
                above = pieces[len(pieces)-columns]
                piece["corners"] = [1 - above["corners"][2], random.randint(0,1), random.randint(0,1), 0]
            
            if piece_type == "right":
                above = pieces[len(pieces)-columns]
                before = pieces[len(pieces)-1]
                piece["corners"] = [1 - above["corners"][2], 0, random.randint(0,1), 1 - before["corners"][1]]
            
            if piece_type == "left_bottom":
                above = pieces[len(pieces)-columns]
                piece["corners"] = [1 - above["corners"][2], random.randint(0,1), 0, 0]
            
            if piece_type == "right_bottom":
                above = pieces[len(pieces)-columns]
                before = pieces[len(pieces)-1]
                piece["corners"] = [1 - above["corners"][2], 0, 0, 1 - before["corners"][1]]
            
            if piece_type == "middle":
                above = pieces[len(pieces)-columns]
                before = pieces[len(pieces)-1]
                piece["corners"] = [1 - above["corners"][2], random.randint(0,1), random.randint(0,1), 1 - before["corners"][1]]
            
            
            mask = os.path.join(os.getcwd(), MASK_FOLDER, "%s_%d_%d_%d_%d.png" % (piece_type, piece["corners"][0], piece["corners"][1], piece["corners"][2], piece["corners"][3]))
            
            piece["mask"] = mask
            pieces.append(piece)
    
    return pieces

def get_memory_size(size):
    
    memoryBytes = size * size * 4;

    memoryKBytes = memoryBytes/1024;
    memoryMBytes = (memoryKBytes/1024) * num_atlases;
    
    return memoryMBytes

# DONE!
def _imagemagick_installed():
    
    try:
        check_call(["composite", "--version"], stdout=open(os.devnull,"w"))
        return True
    except CalledProcessError:
        return False

# DONE! surpress printing
def _texturetools_installed():
    #, stdout=open(os.devnull, 'wb')
    try:
        check_call([TEXTURE_TOOL_PATH, "-h"], stdout=open(os.devnull,"w"))
        return True
    except CalledProcessError:
        return False
        
def _silent_mkdir(dirname):
    try:
        os.mkdir(dirname)
    except OSError, e:
        if e.errno == 17:
            pass
        else:
            raise

if __name__ == "__main__":
    
    parser = OptionParser()
    parser.add_option("-f", "--file", dest="filename",
                      help="specify input image", type="string")
    
    parser.add_option("-s", "--size", dest="size",
                      help="specify a target size for each piece, default 100", type="int", default=100)
    
    parser.add_option("-p", "--padding", dest="padding",
                      help="specify a padding between pieces", type="int", default=2)
    
    (options, args) = parser.parse_args()
    
    sys.exit(0)
    
    # check options
    if options.filename is None:
        print "You need to supply an image file with -f or --file"
        sys.exit(1)
    
    create_pieces(options)