import os
import shutil
import json
import tempfile

from pathlib import Path
from distutils.dir_util import copy_tree
from typing import Dict

import pandas as pd
from styleframe import StyleFrame
from xlrd import XLRDError
from datetime import datetime, timezone
from sparc_me.core.utils import check_row_exist, get_sub_folder_paths_in_folder, validate_metadata_file
from sparc_me.core.metadata import Metadata, Sample, Subject


class Dataset(object):
    def __init__(self):
        DEFAULT_DATASET_VERSION = "2.0.0"
        EXTENSIONS = [".xlsx"]

        self._template_version = DEFAULT_DATASET_VERSION
        self._version = DEFAULT_DATASET_VERSION
        self._current_path = Path(__file__).parent.resolve()
        self._resources_path = Path.joinpath(self._current_path, "../resources")
        self._template_dir = Path()
        self._template = dict()
        self._subjects = {}

        self._dataset_path = Path()
        self._dataset = dict()
        self._metadata_extensions = EXTENSIONS
        self._column_based = ["dataset_description", "code_description"]
        self._subject_id_field = None
        self._sample_id_field = None
        self._metadata: Dict[str, Metadata] = {}

    def set_path(self, path):
        """
        Set the dataset path

        :param path: path to the dataset directory
        :type path: string
        """
        self.set_dataset_path(path)

    def set_dataset_path(self, path):
        """
        Set the path to the dataset

        :param path: path to the dataset directory
        :type path: string
        """
        self._dataset_path = Path(path)
        Sample._dataset_path = self._dataset_path
        Subject._dataset_path = self._dataset_path

    def get_dataset_path(self):
        """
        Return the path to the dataset directory
        :return: path to the dataset directory
        :rtype: string
        """
        return str(self._dataset_path)

    def get_dataset(self):
        """
        :return: current dataset dict
        """
        return self._dataset

    def _get_template_dir(self, version):
        """
        Get template directory path

        :return: path to the template dataset
        :rtype: Path
        """
        version = "version_" + version
        template_dir = self._resources_path / "templates" / version / "DatasetTemplate"

        return template_dir

    def set_template_version(self, version):
        """
        Choose a template version

        :param version: template version
        :type version: string
        """
        version = self._convert_version_format(version)
        self._template_version = version
        self._set_version_specific_variables(version)

    def _set_version_specific_variables(self, version):
        """Set version specific variables

        :param version: SDS version to use Ex: 2_0_0
        :type version: string
        :raises ValueError: if the given version is not an acceptable SDS version
        """
        if version == "2_0_0":
            self._subject_id_field = "subject id"
            self._sample_id_field = "sample id"
        elif version == "1_2_3":
            self._subject_id_field = "subject_id"
            self._sample_id_field = "sample_id"
        else:
            error_msg = f"Unsupported version {version}"
            raise ValueError(error_msg)

    def _load(self, dir_path):
        """
        Load the input dataset into a dictionary

        :param dir_path: path to the dataset dictionary
        :type dir_path: string
        :return: loaded dataset
        :rtype: dict
        """
        dataset = dict()

        dir_path = Path(dir_path)
        for path in dir_path.iterdir():
            if path.suffix in self._metadata_extensions:
                try:
                    metadata = pd.read_excel(path)
                except XLRDError:
                    metadata = pd.read_excel(path, engine='openpyxl')

                metadata = metadata.dropna(how="all")
                metadata = metadata.loc[:, ~metadata.columns.str.contains('^Unnamed')]

                key = path.stem
                value = {
                    "path": path,
                    "metadata": metadata
                }
            else:
                key = path.name
                value = path

            dataset[key] = value

        return dataset

    def create_empty_dataset(self, version='2.0.0'):
        self.load_from_template(version=version)

    def load_from_template(self, version):
        """
        Load dataset from SPARC template

        :param version: template version
        :type version: string
        :return: loaded dataset
        :rtype: dict
        """
        self.set_version(version)
        # self._dataset_path = self._get_template_dir(self._version)
        template_dataset_path = self._get_template_dir(self._version)
        self._dataset = self._load(str(template_dataset_path))

        self._generate_metadata()

    def _convert_version_format(self, version):
        """
        Convert version format
        :param version: dataset/template version
        :type version: string
        :return: version in the converted format
        :rtype:
        """
        version = version.replace(".", "_")

        if "_" not in version:
            version = version + "_0_0"

        return version

    def set_version(self, version):
        """
        Set dataset version version

        :param version: dataset version
        :type version: string
        """
        version = self._convert_version_format(version)

        self._version = version
        self._set_version_specific_variables(version)

    def load_template(self, version):
        """
        Load template

        :param version: template version
        :type version: string
        :return: loaded template
        :rtype: dict
        """

        version = self._convert_version_format(version)
        self.set_template_version(version)
        self._template_dir = self._get_template_dir(self._template_version)
        self._template = self._load(str(self._template_dir))

        return self._template

    def save_template(self, save_dir, version=None):
        """
        Save the template directory locally

        :param save_dir: path to the output folder
        :type save_dir: string
        :param version: template version
        :type version: string
        """
        if version:
            version = self._convert_version_format(version)
            template_dir = self._get_template_dir(version)
        elif not version and self._template_version:
            template_dir = self._get_template_dir(self._template_version)
        else:
            raise ValueError("Template path not found.")

        copy_tree(str(template_dir), str(save_dir))

    def load_dataset(self, dataset_path=None, from_template=False, version=None):
        """
        Load the input dataset into a dictionary

        :param dataset_path: path to the dataset
        :type dataset_path: string
        :param from_template: whether to load the dataset from a SPARC template
        :type from_template: bool
        :param version: dataset version
        :type version: string
        :return: loaded dataset
        :rtype: dict
        """
        if version:
            self.set_version(version)

        if not self._dataset_path:
            self._dataset_path = Path(dataset_path)

        if from_template:
            self._dataset = self.load_from_template(version=version)
        else:
            self._dataset = self._load(dataset_path)
            self._generate_metadata()

        return self._dataset

    def save(self, save_dir="", remove_empty=False, keep_style=False):
        """
        Save dataset

        :param save_dir: path to the dest dir
        :type save_dir: string
        :param remove_empty: (optional) If True, remove rows which do not have values in the "Value" field
        :type remove_empty: bool
        """
        if not self._dataset:
            msg = "Dataset not defined. Please load the dataset or the template dataset in advance."
            raise ValueError(msg)
        if save_dir == "":
            save_dir = self._dataset_path
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        for key, value in self._dataset.items():
            if isinstance(value, dict):
                file_path = Path(value.get("path"))
                filename = file_path.name
                data = value.get("metadata")

                if remove_empty:
                    data = self._filter(data, filename)

                if isinstance(data, pd.DataFrame):
                    self.set_version(self._version)
                    template_dir = self._get_template_dir(self._version)

                    if keep_style:
                        sf = StyleFrame.read_excel_as_template(str(template_dir / filename), data)
                        writer = StyleFrame.ExcelWriter(Path.joinpath(save_dir, filename))
                        sf.to_excel(writer)
                        writer.save()
                    else:
                        data.to_excel(Path.joinpath(save_dir, filename), index=False)

            elif Path(value).is_dir():
                dir_name = Path(value).name
                dir_path = Path.joinpath(save_dir, dir_name)
                copy_tree(str(value), str(dir_path), update=1)

            elif Path(value).is_file():
                filename = Path(value).name
                file_path = Path.joinpath(save_dir, filename)
                try:
                    shutil.copyfile(value, file_path)
                except shutil.SameFileError:
                    # overwrite file by copy, remove then rename
                    file_path_tmp = str(file_path) + "_tmp"
                    shutil.copyfile(value, file_path_tmp)
                    os.remove(file_path)
                    os.rename(file_path_tmp, file_path)

        for gitkeep_path in save_dir.rglob('.gitkeep'):
            gitkeep_path.unlink()

    def load_metadata(self, path):
        """
        Load & update a single metadata

        :param path: path to the metadata file
        :type path: string
        :return: metadata
        :rtype: Pandas.DataFrame
        """
        path = Path(path)
        try:
            metadata = pd.read_excel(path)
        except XLRDError:
            metadata = pd.read_excel(path, engine='openpyxl')

        filename = path.stem
        self._dataset[filename] = {
            "path": path,
            "metadata": metadata
        }

        return metadata

    def _filter(self, metadata, filename):
        """
        Remove column/row if values not set

        :param metadata: metadata
        :type metadata: Pandas.DataFrame
        :param filename: name of the metadata
        :type filename: string
        :return: updated metadata
        :rtype: Pandas.DataFrame
        """
        if "dataset_description" in filename:
            # For the dataset_description metadata, remove rows which do not have values in the "Value" fields
            metadata = metadata.dropna(subset=["Value"])

        return metadata

    def list_metadata_files(self, version, print_list=True):
        """
        list all metadata_files based on the metadata files in the template dataset

        :param version: reference template version
        :type version: string
        :return: all metadata metadata_files
        :rtype: list
        """
        metadata_files = list()

        self.load_template(version=version)

        for key, value in self._template.items():
            if isinstance(value, dict):
                file_path = Path(value.get("path"))
                metadata_file = file_path.stem
                metadata_files.append(metadata_file)

        if print_list:
            print("metadata_files:")
            for metadata_file in metadata_files:
                print(metadata_file)

        return metadata_files

    def list_elements(self, metadata_file, axis=0, version=None):
        """
        List field from a metadata file

        :param metadata_file: metadata metadata_file
        :type metadata_file: string
        :param axis: If axis=0, column-based. list all column headers. i.e. the first row.
                     If axis=1, row-based. list all row index. i.e. the first column in each row
        :type axis: int
        :param version: reference template version
        :type version: string
        :return: a list of fields
        :rtype: list
        """
        fields = None
        metadata_file = validate_metadata_file(metadata_file, version)
        if metadata_file == "dataset_description":
            axis = 1

        if version:
            version = self._convert_version_format(version)
            template_dir = self._get_template_dir(version)

            element_description_file = template_dir / "../schema.xlsx"

            try:
                element_description = pd.read_excel(element_description_file, sheet_name=metadata_file)
            except XLRDError:
                element_description = pd.read_excel(element_description_file, sheet_name=metadata_file,
                                                    engine='openpyxl')

            print("metadata_file: " + str(metadata_file))
            for index, row in element_description.iterrows():
                print(str(row["Element"]))
                print("    Required: " + str(row["Required"]))
                print("    Type: " + str(row["Type"]))
                print("    Description: " + str(row["Description"]))
                print("    Example: " + str(row["Example"]))

            fields = element_description.values.tolist()
            return fields

        if not self._template:
            self.load_template(version=None)

        data = self._template.get(metadata_file)
        metadata = data.get("metadata")
        # set the first column as the index column
        metadata = metadata.set_index(list(metadata)[0])
        if axis == 0:
            fields = list(metadata.columns)
        elif axis == 1:
            fields = list(metadata.index)

        print("Fields:")
        for field in fields:
            print(field)

        return fields

    def _generate_metadata(self):
        metadata_files = self.list_metadata_files(self._version, print_list=False)
        for metadata_file in metadata_files:
            metadata = self._dataset.get(metadata_file).get("metadata")
            self._metadata[metadata_file] = Metadata(metadata_file, metadata, self._version, self._dataset_path)
            if metadata_file == "subjects":
                Subject._metadata = self._metadata[metadata_file]
            elif metadata_file == 'samples':
                Sample._metadata = self._metadata[metadata_file]

        Sample._manifest_metadata = self._metadata['manifest']

    def get_metadata(self, metadata_file):
        """
        :param metadata_file: one of string of [code_description, code_parameters, dataset_description,manifest,performances,resources,samples,subjects,submission]
        :type  metadata_file: string
        :return: give a metadata editor for a specific metadata
        """
        if not self._dataset:
            msg = "Dataset not defined. Please load the dataset in advance."
            raise ValueError(msg)

        metadata_file = validate_metadata_file(metadata_file, self._version)
        return self._metadata[metadata_file]

    def set_field(self, metadata_file, row_index, header, value):
        """
        Set single field by row idx/name and column name (the header)

        :param metadata_file: metadata metadata_file
        :type metadata_file: string
        :param row_index: row index in Excel. Excel index starts from 1 where index 1 is the header row. so actual data index starts from 2
        :type row_index: int
        :param header: column name. the header is the first row
        :type header: string
        :param value: field value
        :type value: string
        :return: updated dataset
        :rtype: dict
        """
        if not self._dataset:
            msg = "Dataset not defined. Please load the dataset in advance."
            raise ValueError(msg)

        metadata = self._dataset.get(metadata_file).get("metadata")

        if not isinstance(row_index, int):
            msg = "row_index should be 'int'."
            raise ValueError(msg)

        try:
            # Convert Excel row index to dataframe index: index - 2
            row_index = row_index - 2
            metadata.loc[row_index, header] = value
        except ValueError:
            msg = "Value error. row does not exists."
            raise ValueError(msg)

        self._dataset[metadata_file]["metadata"] = metadata

        return self._dataset

    def set_field_using_row_name(self, metadata_file, row_name, header, value):
        """
        Set single cell. The row is identified by the given unique name and column is identified by the header.

        :param metadata_file: metadata metadata_file
        :type metadata_file: string
        :param row_name: Unique row name in Excel. (Ex: if subjects is metadata_file, a row name can be a unique subjet id)
        :type row_name: string
        :param header: column name. the header is the first row
        :type header: string
        :param value: field value
        :type value: string
        :return: updated dataset
        :rtype: dict
        """
        if not self._dataset:
            msg = "Dataset not defined. Please load the dataset in advance."
            raise ValueError(msg)

        metadata = self._dataset.get(metadata_file).get("metadata")

        if not isinstance(row_name, str):
            msg = "row_name should be string."
            raise ValueError(msg)

        # Assumes that all excel files first column contains the unique value field
        # TODO: In version 1, the unique column is not the column 0. Hence, unique column must be specified. 
        # This method need to be fixed to accomadate this 
        matching_indices = metadata.index[metadata[metadata.columns[0]] == row_name].tolist()

        if not matching_indices:
            msg = f"No row with given unique name, {row_name}, was found in the unique column {metadata.columns[0]}"
            raise ValueError(msg)
        elif len(matching_indices) > 1:
            msg = f"More than one row with given unique name, {row_name}, was found in the unique column {metadata.columns[0]}"
            raise ValueError(msg)
        else:
            excel_row_index = matching_indices[0] + 2
            return self.set_field(metadata_file=metadata_file, row_index=excel_row_index, header=header, value=value)

    def append(self, metadata_file, row, check_exist=False, unique_column=None):
        """
        Append a row to a metadata file

        :param metadata_file: metadata metadata_file
        :type metadata_file: string
        :param row: a row to be appended
        :type row: dic
        :param check_exist: Check if row exist before appending, if exist, update row, defaults to False
        :type check_exist: bool, optional
        :param unique_column: if check_exist is True, provide which column in metadata_file is unique, defaults to None
        :type unique_column: string, optional
        :raises ValueError: _description_
        :return: updated dataset
        :rtype: dict
        """
        if not self._dataset:
            msg = "Dataset not defined. Please load the dataset in advance."
            raise ValueError(msg)

        # metadata = self._dataset.get(metadata_file).get("metadata")
        current_metadata = self.get_metadata(metadata_file)
        if check_exist:
            # In version 1, the unique column is not the column 0. Hence, unique column must be specified
            if unique_column is None:
                error_msg = "Provide which column in metadata_file is unique. Ex: subject_id"
                raise ValueError(error_msg)

            try:
                row_index = check_row_exist(current_metadata.data, unique_column, unique_value=row[unique_column])
            except ValueError:
                error_msg = "Row values provided does not contain a unique identifier"
                raise ValueError(error_msg)
        else:
            row_index = -1

        if row_index == -1:
            # Add row
            row_df = pd.DataFrame([row])
            current_metadata.data = pd.concat([current_metadata.data, row_df], axis=0,
                                              ignore_index=True)  # If new header comes, it will be added as a new column with its value
        else:
            # Append row with additional values
            for key, value in row.items():
                current_metadata.data.loc[row_index, key] = value

        self._dataset[metadata_file]["metadata"] = current_metadata.data
        return self._dataset

    def update_by_json(self, metadata_file, json_file):
        """
        Given json file, update metadata file
        :param metadata_file: metadata metadata_file/filename
        :type metadata_file: string
        :param json_file: path to metadata file in json
        :type json_file: string
        :return:
        :rtype:
        """
        metadata = self._dataset.get(metadata_file).get("metadata")

        with open(json_file, "r") as f:
            data = json.load(f)

        for key, value in data.items():
            if isinstance(value, dict):
                for key_1, value_1 in value.items():
                    if isinstance(value, list):
                        field = "    " + key_1
                        value = str(value_1)
                    else:
                        field = "    " + key_1
                        value = value_1

                    index = metadata.index[metadata['Metadata element'] == field].tolist()[0]
                    metadata.loc[index, "Value"] = value

            elif isinstance(value, list):
                field = key
                value = str(value)
                index = metadata.index[metadata['Metadata element'] == field].tolist()[0]
                metadata.loc[index, "Value"] = value
            else:
                field = key
                index = metadata.index[metadata['Metadata element'] == field].tolist()[0]
                metadata.loc[index, "Value"] = value

        return metadata

    def generate_file_from_template(self, save_path, metadata_file, data=pd.DataFrame(), keep_style=False):
        """Generate file from a template and populate with data if givn

        :param save_path: destination to save the generated file
        :type save_path: string
        :param metadata_file: SDS metadata_file (Ex: samples, subjects)
        :type metadata_file: string
        :param data: pandas dataframe containing data, defaults to pd.DataFrame()
        :type data: pd.DataFrame, optional
        """

        if keep_style:
            self._template_dir = self._get_template_dir(version=self._version)
            sf = StyleFrame.read_excel_as_template(os.path.join(self._template_dir, f'{metadata_file}.xlsx'), data)
            writer = StyleFrame.ExcelWriter(save_path)
            sf.to_excel(writer)
            writer.save()
        else:
            data.to_excel(save_path, index=False)

    """***************************New Add subjects ***************************"""

    def add_subjects(self, subjects):

        self.save()
        if not isinstance(subjects, list):
            msg = "Please provide a list of subjects"
            raise ValueError(msg)
        for subject in subjects:
            self._subjects[subject.subject_id] = subject
            subject.move()

        self._update_sub_sam_nums_in_dataset_description(self._dataset_path / 'primary')

    def get_subject(self, subject_sds_id) -> Subject:
        """
        Get a subject by subject sds id
        :param subject_sds_id: subject sds id
        :type subject_sds_id: str
        :return: Subject
        """
        if not isinstance(subject_sds_id, str):
            msg = f"Subject not found, please provide a string subject_sds_id!, you subject_sds_id type is {type(subject_sds_id)}"
            raise ValueError(msg)

        try:
            subject = self._subjects.get(subject_sds_id)
            return subject
        except:
            msg = f"Subject not found with {subject_sds_id}! Please check your subject_sds_id in subject metadata file"
            raise ValueError(msg)

    def add_derivative_data(self, source_path, subject, sample, copy=True, overwrite=True):
        """Add raw data of a sample to correct SDS location and update relavent metadata files.
        Requires you to already have the folder structure inplace.

        :param source_path: original location of raw data
        :type source_path: string
        :param subject: subject id
        :type subject: string
        :param sample: sample id
        :type sample: string
        :param sds_parent_dir: path to existing sds dataset parent
        :type sds_parent_dir: string, optional
        :param copy: if True, source directory data will not be deleted after copying, defaults to True
        :type copy: bool, optional
        :param overwrite: if True, any data in the destination folder will be overwritten, defaults to False
        :type overwrite: bool, optional
        :raises NotADirectoryError: if the derivative in sds_parent_dir is not a folder, this wil be raised.
        """

        derivative_folder = os.path.join(str(self._dataset_path), 'derivative')

        # Check if sds_parent_directory contains the derivative folder. If not create it.
        if os.path.exists(derivative_folder):
            if not os.path.isdir(derivative_folder):
                raise NotADirectoryError(f'{derivative_folder} is not a directory')
        else:
            os.mkdir(derivative_folder)

        self._add_sample_data(source_path, self._dataset_path, subject, sample, data_type="derivative", copy=copy,
                              overwrite=overwrite)

    def add_element(self, metadata_file, element):
        metadata = self._dataset.get(metadata_file).get("metadata")
        if metadata_file in self._column_based:
            row_pd = pd.DataFrame([{"Metadata element": element}])
            metadata = pd.concat([metadata, row_pd], axis=0, ignore_index=True)
        else:
            metadata[element] = None

        self._dataset[metadata_file]["metadata"] = metadata

    def add_thumbnail(self, source_path, copy=True, overwrite=True):

        file_source_path = Path(source_path)
        if not file_source_path.is_file():
            msg = f"source_path should be the thumbnail file's path"
            raise ValueError(msg)
        else:
            filename = file_source_path.name
            destination_path = self._dataset_path.joinpath('docs', filename)
            if destination_path.exists():
                if overwrite:
                    self._delete_data(destination_path)
                else:
                    msg = f"The thumbnail file has already in primary folder"
                    raise FileExistsError(msg)

            self._move_single_file(file_path=source_path, destination_path=destination_path, fname=filename, copy=copy)
            description = f"This is a thumbnail file"
            self._modify_manifest(fname=filename, manifest_folder_path=str(self._dataset_path),
                                  destination_path=str(destination_path.parent), description=description)

    def _add_sample_data(self, source_path, dataset_path, subject, sample, data_type="primary", copy=True,
                         overwrite=True):
        """Copy or move data from source folder to destination folder

        :param source_path: path to the original data
        :type source_path: string
        :param destination_path_list: folder path in a list[root, data_pype, subject, sample] to be copied into
        :type destination_path_list: list
        :param copy: if True, source directory data will not be deleted after copying, defaults to True
        :type copy: bool, optional
        :param overwrite: if True, any data in the destination folder will be overwritten, defaults to False
        :type overwrite: bool, optional
        :raises FileExistsError: if the destination folder contains data and overwritten is set to False, this wil be raised.
        """
        destination_path = os.path.join(str(dataset_path), data_type, subject, sample)
        # If overwrite is True, remove existing sample
        if os.path.exists(destination_path):
            if os.path.isdir(source_path):
                if overwrite:
                    shutil.rmtree(destination_path)
                    os.makedirs(destination_path)
                else:
                    raise FileExistsError(
                        "Destination file already exist. Indicate overwrite argument as 'True' to overwrite the existing")
            else:
                if overwrite:
                    file_path = Path(destination_path).joinpath(Path(source_path).name)
                    self._delete_data(file_path)
                else:
                    raise FileExistsError(
                        "Destination file already exist. Indicate overwrite argument as 'True' to overwrite the existing")
        else:
            # Create destination folder
            os.makedirs(destination_path)

        description = f"File of subject {subject} sample {sample}"
        if os.path.isdir(source_path):
            for fname in os.listdir(source_path):
                file_path = os.path.join(source_path, fname)
                if os.path.isdir(file_path):
                    # Warn user if a subdirectory exist in the input_path
                    print(
                        f"Warning: Input directory consist of subdirectory {source_path}. It will be avoided during copying")
                    return
                else:
                    self._move_single_file(file_path=file_path, destination_path=destination_path,
                                           fname=fname, copy=copy)
                    self._modify_manifest(fname=fname, manifest_folder_path=dataset_path,
                                          destination_path=destination_path,
                                          description=description)
        else:
            fname = os.path.basename(source_path)
            self._move_single_file(file_path=source_path, destination_path=destination_path,
                                   fname=fname, copy=copy)
            self._modify_manifest(fname=fname, manifest_folder_path=dataset_path, destination_path=destination_path,
                                  description=description)

    def _move_single_file(self, file_path, destination_path, fname, copy):
        if copy:
            # Copy data
            shutil.copy2(file_path, destination_path)
        else:
            # Move data
            shutil.move(file_path, os.path.join(destination_path, fname))

    def _modify_manifest(self, fname, manifest_folder_path, destination_path, description=""):
        # Check if manifest exist
        # If can be "xlsx", "csv" or "json"
        files = os.listdir(manifest_folder_path)
        manifest_file_path = [f for f in files if "manifest" in f]
        # Case 1: manifest file exists
        if len(manifest_file_path) != 0:
            manifest_file_path = os.path.join(manifest_folder_path, manifest_file_path[0])
            # Check the extension and read file accordingly
            extension = os.path.splitext(manifest_file_path)[-1].lower()
            if extension == ".xlsx":
                df = pd.read_excel(manifest_file_path)
            elif extension == ".csv":
                df = pd.read_csv(manifest_file_path)
            elif extension == ".json":
                # TODO: Check what structure a manifest json is in
                # Below code assumes json structure is like
                # '{"row 1":{"col 1":"a","col 2":"b"},"row 2":{"col 1":"c","col 2":"d"}}'
                df = pd.read_json(manifest_file_path, orient="index")
            else:
                raise ValueError(f"Unauthorized manifest file extension: {extension}")
        # Case 2: create manifest file
        else:
            # Default extension to xlsx
            extension = ".xlsx"
            # Creat manifest file path
            manifest_file_path = os.path.join(manifest_folder_path, "manifest.xlsx")
            df = pd.DataFrame(columns=['filename', 'description', 'timestamp', 'file type'])

        file_path = Path(
            str(os.path.join(destination_path, fname)).replace(str(manifest_folder_path), '')[1:]).as_posix()

        row = {
            'filename': file_path,
            'timestamp': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            'description': description,
            'file type': os.path.splitext(fname)[-1].lower()[1:]
        }

        exsiting_row = df['filename'] == row['filename']
        if exsiting_row.any():
            df.loc[exsiting_row, 'timestamp'] = row['timestamp']
        else:
            row_pd = pd.DataFrame([row])
            df = pd.concat([df, row_pd], axis=0, ignore_index=True)

        # update dataset metadata
        self._update_dataset_by_df(df, "manifest")

        # Save editted manifest file
        if extension == ".xlsx":
            df.to_excel(manifest_file_path, index=False)
        elif extension == ".csv":
            df = pd.to_csv(manifest_file_path, index=False)
        elif extension == ".json":
            df = pd.read_json(manifest_file_path, orient="index")
        return

    def _update_dataset_by_df(self, df, metadata_file):
        manifest_metadata = self._metadata[metadata_file]
        manifest_metadata.data = df
        self._dataset[metadata_file]["metadata"] = manifest_metadata.data

    """************************************ Delete Data Functions ************************************"""

    def delete_subjects(self, destination_paths, data_type="primary"):
        """
        :param destination_paths: the subject folder paths that you want to delete
        :type destination_paths: str[]
        :param data_type: "primary" | "derivative"
        :type: str
        :return:
        """
        if isinstance(destination_paths, list):
            for sub_folder in destination_paths:
                self.delete_subject(destination_path=sub_folder, data_type=data_type)
        else:
            msg = f"Please provide a list, and put all your deleting sample paths in a list"
            raise ValueError(msg)

    def delete_subject(self, destination_path, data_type="primary"):
        """
        :param destination_path: the subject folder path that you want to delete
        :type destination_path: str
        :param data_type: "primary" | "derivative"
        :type: str
        :return:
        """
        if isinstance(destination_path, list):
            msg = f"Please provide a path string!"
            raise ValueError(msg)

        sub_folder = Path(destination_path)
        if not sub_folder.exists():
            msg = f"The folder {sub_folder} is not existing"
            raise ValueError(msg)
        elif not sub_folder.is_dir():
            msg = f"The {sub_folder} is not a folder"
            raise ValueError(msg)
        else:
            primary_folder = self._dataset_path / "primary"
            for sam_folder in sub_folder.iterdir():
                if sam_folder.is_dir():
                    self.delete_sample(sam_folder, data_type)

            sub_folder.rmdir()
            if data_type == "primary":
                self._update_sub_sam_nums_in_dataset_description(primary_folder)
                subjects_metadata = self._metadata["subjects"]
                subjects_metadata.remove_row(sub_folder.name)
                subjects_metadata.save()

    def delete_samples(self, destination_paths, data_type="primary"):
        """
        :param destination_paths: a list of deleting sample folders
        :type destination_paths: list
        :param data_type: "primary" | "derivative"
        :type data_type: str
        :return:
        """
        if isinstance(destination_paths, list):
            for sam_folder in destination_paths:
                self.delete_sample(destination_path=sam_folder, data_type=data_type)
        else:
            msg = f"The {destination_paths} type is {type(destination_paths)}. Please provide a list, and put all your deleting sample paths in a list"
            raise TypeError(msg)

    def delete_sample(self, destination_path, data_type="primary"):
        """
        :param destination_path: the sample folder path that you want to delete
        :param data_type:
        :return:
        """
        if isinstance(destination_path, list):
            msg = f"Please provide a path string!"
            raise TypeError(msg)

        sam_folder = Path(destination_path)
        if not sam_folder.exists():
            msg = f"The folder {sam_folder} is not existing"
            raise FileExistsError(msg)
        elif not sam_folder.is_dir():
            msg = f"The {sam_folder} path is not a folder, please provide the sample files folder."
            raise ValueError(msg)
        else:
            primary_folder = self._dataset_path / "primary"
            for item in sam_folder.iterdir():
                self.delete_data(item)
            sam_folder.rmdir()
            if data_type == "primary":
                self._update_sub_sam_nums_in_dataset_description(primary_folder)
                samples_metadata = self._metadata["samples"]
                samples_metadata.remove_row(sam_folder.name)
                samples_metadata.save()

    def delete_data(self, destination_path):
        if not Path(destination_path).exists():
            msg = f"The file {str(destination_path)} is not existing"
            raise FileNotFoundError(msg)
        else:
            delete_flag = self._delete_data(destination_path)
            if delete_flag:
                path = str(Path(str(Path(destination_path).as_posix()).replace(str(self._dataset_path.as_posix()), "")[
                                1:]).as_posix())
                manifest = self._metadata["manifest"]
                manifest.remove_row(path)
                manifest.save()

    def _delete_data(self, destination_path):
        file_path = Path(destination_path)
        if file_path.exists():
            if file_path.is_file():
                file_path.unlink()
                return True
            else:
                shutil.rmtree(file_path)
                return False
        else:
            return False

    def _update_sub_sam_nums_in_dataset_description(self, primary_folder):
        """
        :param primary_folder: the primary folder url
        :type: Path|str
        :return:
        """
        subject_folders = get_sub_folder_paths_in_folder(primary_folder)
        sample_folders = []
        for sub in subject_folders:
            if sub.is_dir():
                folders = get_sub_folder_paths_in_folder(sub)
                sample_folders.extend(folders)
        dataset_description_metadata = self._metadata["dataset_description"]
        dataset_description_metadata.set_values(element="Number of subjects", values=len(subject_folders))
        dataset_description_metadata.set_values(element="Number of samples", values=len(sample_folders))
        dataset_description_metadata.save()
