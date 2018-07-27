import os
import subprocess
import shutil
import platform

from eplaunch.workflows.base import BaseEPLaunch3Workflow, EPLaunch3WorkflowResponse
from eplaunch.utilities.version import Version


class TransitionWorkflow(BaseEPLaunch3Workflow):

    def name(self):
        return "Transition"

    def description(self):
        return "Run Version Transition"

    def get_file_types(self):
        return ["*.idf"]

    def get_output_suffixes(self):
        return [".vcperr"]

    def get_extra_data(self):
        return {"Hey, it's extra": "data"}

    def main(self, run_directory, file_name, args):
        print(args['workflow location'])
        self.versionclass = Version()
        if 'workflow location' in args:
            self.transition_executable_files = self.find_transition_executable_files(args['workflow location'])
            if self.transition_executable_files:
                print(self.transition_executable_files)
                full_file_path = os.path.join(run_directory, file_name)
                if os.path.exists(full_file_path):
                    returned_success, returned_message = self.perform_transition(full_file_path)
                    return EPLaunch3WorkflowResponse(
                         success=returned_success,
                         message=returned_message,
                         column_data=[]
                     )
                else:
                    return EPLaunch3WorkflowResponse(
                        success=False,
                        message="Transition file not found: {}!".format(''),
                        column_data=[]
                    )
            else:
                return EPLaunch3WorkflowResponse(
                    success=False,
                    message="Transition exefile not found: {}!".format(''),
                    column_data=[]
                )
        else:
            return EPLaunch3WorkflowResponse(
                success=False,
                message="Workflow location missing: {}!".format(args['worflow location']),
                column_data=[]
            )

    def find_transition_executable_files(self, worflow_location):
        energyplus_root_folder, _ = os.path.split(worflow_location)
        preprocess_folder = os.path.join(energyplus_root_folder, 'PreProcess')
        idfversionupdateer_folder = os.path.join(preprocess_folder, 'IDFVersionUpdater')
        transition_exes = [os.path.join(idfversionupdateer_folder, f) for f in os.listdir(idfversionupdateer_folder) if 'Transition-V' in f]
        transition_exes.sort()
        transition_dict = {}
        for transition_exe in transition_exes:
            start_number, end_number = self.get_start_end_version_from_exe(transition_exe)
            transition_dict[start_number] = [end_number, transition_exe]
        return transition_dict

    def get_start_end_version_from_exe(self, exe_file_name):
        if '\\' in exe_file_name:
            parts = exe_file_name.split('\\')
            filename = parts[-1]
        else:
            filename = exe_file_name
        # Transition-V8-8-0-to-V8-9-0.exe
        # 01234567890123456789012345678901234567890
        if filename[:11] == 'Transition-':
            versions_string_with_ext = filename[11:]
            versions_string, _ = versions_string_with_ext.split('.')
            start_version, end_version = versions_string.split('-to-')
            start_number = self.versionclass.numeric_version_from_dash_string(start_version)
            end_number = self.versionclass.numeric_version_from_dash_string(end_version)
            return start_number, end_number
        else:
            return 0, 0

    def perform_transition(self, path_to_old_file):
        v = Version()
        is_version_found, original_version_string, original_version_number = v.check_energyplus_version(path_to_old_file)
        print(is_version_found, original_version_string, original_version_number)
        if original_version_number in self.transition_executable_files:
            current_version_number = original_version_number
            while current_version_number in self.transition_executable_files:
                current_version_string = v.string_version_from_number(current_version_number)
                next_version_number, specific_transition_exe = self.transition_executable_files[current_version_number]
                self.run_single_transition(specific_transition_exe, path_to_old_file, current_version_string)
                current_version_number = next_version_number
            final_version_string = v.string_version_from_number(current_version_number)
            return True, 'Version update successful for IDF file {} originally version {} and now version {}'.format(path_to_old_file, original_version_string, final_version_string)
        else:
            return False, 'Updating the IDF file {} that is from version {} is not supported.'.format(path_to_old_file, original_version_string)

    def run_single_transition(self, transition_exe_path, file_to_update, old_verson_string):
        file_no_extension, _ = os.path.splitext(file_to_update)
        run_directory, _ = os.path.split(transition_exe_path)
        command_line_args = [transition_exe_path, file_to_update]
        idf_copy_of_old_file_temp = file_to_update + '_tempcopy'
        # make temporary copy that preserve file date
        shutil.copy2(file_to_update, idf_copy_of_old_file_temp)
        # see if rvi file is used
        orig_rvi_file = file_no_extension + '.rvi'
        if os.path.exists(orig_rvi_file):
            rvi_copy_of_old_file_temp = file_no_extension + '.rvi_tempcopy'
            shutil.copy2(orig_rvi_file, rvi_copy_of_old_file_temp)
        # see if mvi file is used
        orig_mvi_file = file_no_extension + '.mvi'
        if os.path.exists(orig_mvi_file):
            mvi_copy_of_old_file_temp = file_no_extension + '.mvi_tempcopy'
            shutil.copy2(orig_mvi_file, mvi_copy_of_old_file_temp)
        # perform transition
        process = subprocess.run(
            command_line_args,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=run_directory
        )
        if process.returncode == 0:
            print('convertion complete')
            # delete the extra outputs that are not needed
            idfnew_path = file_no_extension + '.idfnew'
            if os.path.exists(idfnew_path):
                os.remove(idfnew_path)
                idfold_path = file_no_extension + '.idfold'
                if os.path.exists(idfold_path):
                    os.remove(idfold_path)
                # rename the previously copied file to preserve the old version
                idf_revised_old_path = file_no_extension + '_' + old_verson_string + '.idf'
                if os.path.exists(idf_copy_of_old_file_temp):
                    os.rename(idf_copy_of_old_file_temp, idf_revised_old_path)
                # work on the rvi update
                rvinew_path = file_no_extension + '.rvinew'
                if os.path.exists(rvinew_path):
                    os.remove(rvinew_path)
                rviold_path = file_no_extension + '.rviold'
                if os.path.exists(rviold_path):
                    os.remove(rviold_path)
                rvi_revised_old_path = file_no_extension + '_' + old_verson_string + '.rvi'
                if os.path.exists(orig_rvi_file):
                    os.rename(rvi_copy_of_old_file_temp, rvi_revised_old_path)
                # work on the rvi update
                mvinew_path = file_no_extension + '.mvinew'
                if os.path.exists(mvinew_path):
                    os.remove(mvinew_path)
                mviold_path = file_no_extension + '.mviold'
                if os.path.exists(mviold_path):
                    os.remove(mviold_path)
                mvi_revised_old_path = file_no_extension + '_' + old_verson_string + '.mvi'
                if os.path.exists(orig_mvi_file):
                    os.rename(mvi_copy_of_old_file_temp, mvi_revised_old_path)
                # process any error file
                vcperr_file = file_no_extension + '.vcperr'
                if os.path.exists(vcperr_file):
                    vcperr_revised_file = file_no_extension + '_' + old_verson_string + '.vcperr'
                    os.rename(vcperr_file, vcperr_revised_file)
                return True
            else:
                print('convertion problem-2', transition_exe_path, file_to_update)
                return False
        else:
            print('convertion problem-1', transition_exe_path, file_to_update)
            return False
