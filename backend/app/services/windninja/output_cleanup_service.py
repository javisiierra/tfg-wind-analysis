import glob
import os

def delete_format_files(path_output):
    # delete all .prj files
    ################################
    files_to_delete = glob.glob(os.path.join(path_output, "*.prj"))
    for file_path in files_to_delete:
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")

    # delete all *cld.asc
    ###############################
    files_to_delete = glob.glob(os.path.join(path_output, '*cld.asc'))
    for file in files_to_delete:
        try:
            os.remove(file)
        except Exception as e:
            print(f"Failed to delete {file}: {e}")