# import os

# import pytest
# from pyparse import parsers
# from pyparse.schemas import data

# asset_dir = os.path.join(os.path.dirname(__file__), "assets")

# FILES = {"eml": ["test.eml"], "img": ["test.jpg"], "txt": ["test.txt"]}


# class TestFile:
#     @pytest.mark.parametrize("file_name", FILES["eml"])
#     def test_email(self, file_name):
#         actual = parsers.EmlParser.parse(os.path.join(asset_dir, file_name))
#         assert data.Email(**actual)

#     @pytest.mark.parametrize("file_name", FILES["img"])
#     def test_image(self, file_name):
#         actual = parsers.ImageParser.parse(os.path.join(asset_dir, file_name))
#         assert data.Image(**actual)

#     @pytest.mark.parametrize("file_name", FILES["txt"])
#     def test_txt(self, file_name):
#         actual = parsers.TxtParser.parse(os.path.join(asset_dir, file_name))
#         assert data.Document(**actual)
