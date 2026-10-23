from PIL import ImageFile

# Decode what's there of photos missing their last few bytes instead of failing them.
ImageFile.LOAD_TRUNCATED_IMAGES = True
