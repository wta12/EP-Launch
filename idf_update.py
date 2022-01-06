import sys,os,glob
from shutil import copyfile
import shutil, uuid
sys.path.append('/home/EP_DevDir/EP-Launch')

import eplaunch

from eplaunch.utilities.locateworkflows import LocateWorkflows
from eplaunch.workflows import manager as workflow_manager
from eplaunch.utilities.version import Version

def_ep_workflow_path = '/home/EP_DevDir/EP_Install/9_6/workflows'

# ## Get workflow folder
# locateworkflow_task = LocateWorkflows()
# locateworkflow_task.find_eplus_workflows()
# locateworkflow_task.list_of_found_directories.add(def_ep_workflow_path)
# locateworkflow_task.get_energyplus_versions()
# (locateworkflow_task.get_workflow_directory("9.6"))


# ## get workflow_detail for transitions
# workflow_details = workflow_manager.get_workflows(locateworkflow_task.list_of_found_directories)
# update_transition = [i for i in workflow_details[0] if i.description.startswith("Transition") ][0]
# print(update_transition)

sys.path.append(def_ep_workflow_path)

from transition import TransitionWorkflow
run_directory = '/home/EP_DevDir/Dev_Works/Output'
args = {'workflow location' : def_ep_workflow_path}
file_name = '5Zone_IdealLoadsAirSystems_ReturnPlenum.idf'
file_name = 'in_ok.idf'
source_directory = '/home/EP_DevDir/Dev_Works/Input'
input_file_path = os.path.join(run_directory,file_name)
for files in os.listdir(run_directory):
    path = os.path.join(run_directory, files)
    try:
        shutil.rmtree(path)
    except OSError:
        os.remove(path)
 
if os.path.exists(input_file_path):
    os.remove(input_file_path)
copyfile(os.path.join(source_directory,file_name), input_file_path)
new_uuid = str(uuid.uuid4())

input_file = os.path.join(run_directory,file_name)
transition_task = TransitionWorkflow()
transition_task.versionclass = Version()
transition_task.transition_executable_files = transition_task.find_transition_executable_files(args['workflow location']) ## find transition program
# transition_task.my_id = new_uuid 
transition_task.perform_transition( input_file)