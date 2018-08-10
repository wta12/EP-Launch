import fnmatch
import json
import os
import uuid
from gettext import gettext as _

import wx

from wx.lib.pubsub import pub

from eplaunch.interface import workflow_directories_dialog
from eplaunch.interface.externalprograms import EPLaunchExternalPrograms
from eplaunch.interface.frame_support import FrameSupport
from eplaunch.interface.filenamemenus import FileNameMenus
from eplaunch.interface.workflow_output_dialog import Dialog as OutputDialog
from eplaunch.interface.workflow_processing import event_result, WorkflowThread
from eplaunch.utilities.cache import CacheFile
from eplaunch.utilities.crossplatform import Platform
from eplaunch.utilities.exceptions import EPLaunchDevException, EPLaunchFileException
from eplaunch.utilities.filenamemanipulation import FileNameManipulation
from eplaunch.utilities.locateworkflows import LocateWorkflows
from eplaunch.workflows import manager as workflow_manager


# wx callbacks need an event argument even though we usually don't use it, so the next line disables that check
# noinspection PyUnusedLocal
class EpLaunchFrame(wx.Frame):
    DefaultSize = (650, 600)

    def __init__(self, *args, **kwargs):

        kwargs["style"] = wx.DEFAULT_FRAME_STYLE

        wx.Frame.__init__(self, *args, **kwargs)

        # Set the title!
        self.SetTitle(_("EP-Launch 3"))

        # set the window exit
        self.Bind(wx.EVT_CLOSE, self.handle_frame_close)

        # Get saved settings
        self.config = wx.Config("EP-Launch3")

        # Get an instance of the supporting function class
        self.support = FrameSupport()

        # initialize these here (and early) in the constructor to hush up the compiler messages
        self.primary_toolbar = None
        self.output_toolbar = None
        self.tb_run = None
        self.menu_file_run = None
        self.menu_bar = None
        self.current_workflow = None
        self.work_flows = None
        self.selected_directory = None
        self.selected_file = None
        self.menu_output_toolbar = None
        self.status_bar = None
        self.raw_file_list = None
        self.control_file_list = None
        self.current_cache = None
        self.current_weather_file = None
        self.output_toolbar_icon_size = None
        self.directory_tree_control = None
        self.file_lists_splitter = None
        self.control_file_list_panel = None
        self.raw_file_list_panel = None
        self.folder_menu = None
        self.folder_recent = None
        self.folder_favorites = None
        self.weather_menu = None
        self.weather_recent = None
        self.weather_favorites = None
        self.output_menu = None
        self.extra_output_menu = None
        self.tb_idf_editor_id = None
        self.output_menu_item = None
        self.extra_output_menu_item = None
        self.current_selected_version = None
        self.current_workflow_directory = None
        self.option_version_menu = None
        self.help_menu = None
        self.workflow_choice = None
        self.energyplus_workflow_directories = None
        self.workflow_directories = None

        # this is a map of the background workers, using a uuid as a key
        self.workflow_threads = {}

        # this is a map of workflow output dialogs, using the uuid as a key
        self.workflow_output_dialogs = {}
        self.workflow_dialog_counter = 0  # a simple counter ultimately used to place dialogs on the screen

        # get the saved workflow directories and update the main workflow list
        self.retrieve_workflow_directories_config()
        self.locate_workflows = LocateWorkflows()
        self.list_of_versions = self.locate_workflows.get_energyplus_versions()
        self.update_workflow_list()

        # build out the whole GUI and do other one-time init here
        self.gui_build()
        self.reset_raw_list_columns()
        self.update_num_processes_status()

        # this sets up an event handler for workflow completion and callback events
        event_result(self, self.handle_workflow_done)
        pub.subscribe(self.workflow_callback, "workflow_callback")

        # these are things that need to be done frequently
        self.update_control_list_columns()
        self.update_file_lists()
        self.update_workflow_dependent_menu_items()

        # get the saved active directory
        self.retrieve_current_directory_config()

        # create external program runner
        self.external_runner = EPLaunchExternalPrograms()

        # create file name manipulation object
        self.file_name_manipulator = FileNameManipulation()

# Frame Object Manipulation

    def update_workflow_list(self, filter_version=None):
        self.energyplus_workflow_directories = self.locate_workflows.find()
        self.work_flows = workflow_manager.get_workflows(
            external_workflow_directories=self.energyplus_workflow_directories
        )
        if filter_version:
            self.work_flows = [w for w in self.work_flows if w.version_id == filter_version]

    def update_workflow_dependent_menu_items(self):
        if not self.current_workflow:
            return
        self.menu_output_toolbar.SetText("%s Output Toolbar..." % self.current_workflow.name)
        self.update_output_menu()
        self.update_output_toolbar()

    def update_output_menu(self):
        # remove all the old menu items first
        old_menu_items = self.output_menu.GetMenuItems()
        for old_menu_item in old_menu_items:
            old_id = old_menu_item.GetId()
            self.output_menu.Delete(old_id)
        # all all the new menu items
        if self.current_workflow:
            output_suffixes = self.current_workflow.output_suffixes
        else:
            output_suffixes = []
        output_suffixes.sort()
        number_of_items_in_main = 30
        if len(output_suffixes) < number_of_items_in_main:
            for count, suffix in enumerate(output_suffixes):
                self.output_menu_item = self.output_menu.Append(500 + count, suffix)
                self.Bind(wx.EVT_MENU, self.handle_output_menu_item, self.output_menu_item)
        else:
            main_suffixes = output_suffixes[:number_of_items_in_main]
            extra_suffixes = output_suffixes[number_of_items_in_main:]
            for count, suffix in enumerate(main_suffixes):
                self.output_menu_item = self.output_menu.Append(500 + count, suffix)
                self.Bind(wx.EVT_MENU, self.handle_output_menu_item, self.output_menu_item)
            self.extra_output_menu = wx.Menu()
            for count, suffix in enumerate(extra_suffixes):
                self.extra_output_menu_item = self.extra_output_menu.Append(550 + count, suffix)
                self.Bind(wx.EVT_MENU, self.handle_extra_output_menu_item, self.extra_output_menu_item)
            self.output_menu.Append(549, "Extra", self.extra_output_menu)

    def update_output_toolbar(self):
        # remove all the old menu items first
        self.output_toolbar.ClearTools()
        # add tools based on the workflow
        norm_bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_TOOLBAR, self.output_toolbar_icon_size)
        tb_output_suffixes = []
        if self.current_workflow:
            output_suffixes = self.current_workflow.output_suffixes
        else:
            output_suffixes = []
        for item in output_suffixes:
            tb_output_suffixes.append(item)
        for count, tb_output_suffix in enumerate(tb_output_suffixes):
            out_tb_button = self.output_toolbar.AddTool(
                10 + count, tb_output_suffix, norm_bmp, wx.NullBitmap, wx.ITEM_NORMAL, tb_output_suffix,
                "Open the file ending with " + tb_output_suffix,
                None
            )
            self.output_toolbar.Bind(wx.EVT_TOOL, self.handle_out_tb_button, out_tb_button)
            if count % 3 == 2:
                self.output_toolbar.AddSeparator()
        self.output_toolbar.Realize()

    def update_control_list_columns(self):
        self.control_file_list.DeleteAllColumns()
        self.control_file_list.AppendColumn(_("File Name"), format=wx.LIST_FORMAT_LEFT, width=-1)
        self.control_file_list.AppendColumn(_("Weather File"), format=wx.LIST_FORMAT_LEFT, width=-1)
        if not self.current_workflow:
            return
        for current_column in self.current_workflow.columns:
            self.control_file_list.AppendColumn(_(current_column), format=wx.LIST_FORMAT_LEFT, width=-1)

    def reset_raw_list_columns(self):
        self.raw_file_list.AppendColumn(_("File Name"), format=wx.LIST_FORMAT_LEFT, width=-1)
        self.raw_file_list.AppendColumn(_("Date Modified"), format=wx.LIST_FORMAT_LEFT, width=-1)
        self.raw_file_list.AppendColumn(_("Size"), format=wx.LIST_FORMAT_RIGHT, width=-1)

    def update_file_lists(self):

        # if we don't have a directory name, it's probably during init, just ignore
        if not self.selected_directory:
            return

        # get the local cache file path for this folder
        cache_file = CacheFile(self.selected_directory)

        # if there is a cache file there, read the cached file data for the current workflow
        if self.current_workflow:
            files_in_current_workflow = cache_file.get_files_for_workflow(
                self.current_workflow.name
            )
            workflow_file_patterns = self.current_workflow.file_types
            workflow_columns = self.current_workflow.columns
        else:
            files_in_current_workflow = []
            workflow_file_patterns = []
            workflow_columns = []

        # then get the entire list of files in the current directory to build up the listview items
        # if they happen to match the filename in the workflow cache, then add that info to the row structure
        files_in_dir = self.support.get_files_in_directory(self.selected_directory)
        control_list_rows = []
        raw_list_rows = []
        for file_structure in files_in_dir:
            # verify the quality of the response from the get_files routine
            if not all([x in file_structure for x in ['name', 'size', 'modified']]):
                raise EPLaunchDevException('Developer issue: malformed response from get_files_in_directory')
            # always add the columns to the raw list for all files
            file_name = file_structure['name']
            file_size = file_structure['size']
            file_modified = file_structure['modified']
            raw_list_rows.append([file_name, file_modified, file_size])
            # but only include this row if the file matches the workflow pattern
            matched = False
            for file_type in workflow_file_patterns:
                if fnmatch.fnmatch(file_name, file_type):
                    matched = True
                    break
            if not matched:
                continue
            # listview row always includes the filename itself, so start the array with that
            row = [file_name]
            # if it in the cache then the listview row can include additional data
            if file_name in files_in_current_workflow:
                cached_file_info = files_in_current_workflow[file_name]
                if CacheFile.ParametersKey in cached_file_info:
                    if CacheFile.WeatherFileKey in cached_file_info[CacheFile.ParametersKey]:
                        full_weather_path = cached_file_info[CacheFile.ParametersKey][CacheFile.WeatherFileKey]
                        row.append(os.path.basename(full_weather_path))
                    else:
                        row.append('<no_weather_files>')
                else:
                    row.append('<no_weather_file>')
                if CacheFile.ResultsKey in cached_file_info:
                    for column in workflow_columns:
                        if column in cached_file_info[CacheFile.ResultsKey]:
                            row.append(cached_file_info[CacheFile.ResultsKey][column])

            # always add the row to the main list
            control_list_rows.append(row)

        # clear all items from the listview and then add them back in
        self.control_file_list.DeleteAllItems()
        for row in control_list_rows:
            self.control_file_list.Append(row)
        self.control_file_list.SetColumnWidth(0, -1)  # autosize column width

        # clear all the items from the raw list as well and add all of them back
        self.raw_file_list.DeleteAllItems()
        for row in raw_list_rows:
            self.raw_file_list.Append(row)
        self.raw_file_list.SetColumnWidth(0, -1)
        self.raw_file_list.SetColumnWidth(1, -1)

    def update_num_processes_status(self):
        self.status_bar.SetStatusText("Currently %s processes running" % len(self.workflow_threads), i=2)

    def refresh_workflow_selection(self, workflow_to_match):
        if not self.work_flows:
            self.current_workflow = None
        else:
            previous_workflow = self.config.Read('/ActiveWindow/SelectedWorkflow')
            # if blank try to set the workflow to something with the word EnergyPlus in it
            if not previous_workflow:
                energyplus_workflows = [x for x in self.work_flows if 'ENERGYPLUS' in x.name().upper()]
                if energyplus_workflows:
                    previous_workflow = energyplus_workflows[0]
            if previous_workflow:
                found = False
                for workflow_index, workflow_choice in enumerate(self.work_flows):
                    if workflow_to_match == workflow_choice.name:
                        self.current_workflow = self.work_flows[workflow_index]
                        self.workflow_choice.SetSelection(workflow_index)
                        found = True
                        break
                if not found:
                    self.current_workflow = self.work_flows[0]
                    self.workflow_choice.SetSelection(0)
            else:
                self.current_workflow = self.work_flows[0]
                self.workflow_choice.SetSelection(0)

    def update_output_file_status(self):
        file_name_no_ext, extension = os.path.splitext(self.selected_file)
        full_path_name_no_ext = os.path.join(self.selected_directory, file_name_no_ext)
        self.disable_output_menu_items()
        self.enable_existing_menu_items(full_path_name_no_ext)
        self.disable_output_toolbar_buttons()
        self.enable_existing_output_toolbar_buttons(full_path_name_no_ext)

    def disable_output_menu_items(self):
        output_menu_items = self.output_menu.GetMenuItems()
        for output_menu_item in output_menu_items:
            if output_menu_item.GetLabel() != "Extra":
                output_menu_item.Enable(False)
        if self.extra_output_menu is not None:
            extra_output_menu_items = self.extra_output_menu.GetMenuItems()
            for extra_output_menu_item in extra_output_menu_items:
                extra_output_menu_item.Enable(False)

    def enable_existing_menu_items(self, path_no_ext):
        output_menu_items = self.output_menu.GetMenuItems()
        for output_menu_item in output_menu_items:
            if output_menu_item.GetLabel() != "Extra":
                if os.path.exists(path_no_ext + output_menu_item.GetLabel()):
                    output_menu_item.Enable(True)
        if self.extra_output_menu is not None:
            extra_output_menu_items = self.extra_output_menu.GetMenuItems()
            for extra_output_menu_item in extra_output_menu_items:
                if os.path.exists(path_no_ext + extra_output_menu_item.GetLabel()):
                    extra_output_menu_item.Enable(True)

    def disable_output_toolbar_buttons(self):
        number_of_tools = self.output_toolbar.GetToolsCount()
        for tool_num in range(number_of_tools):
            cur_tool = self.output_toolbar.GetToolByPos(tool_num)
            cur_id = cur_tool.GetId()
            self.output_toolbar.EnableTool(cur_id, False)
        self.output_toolbar.Realize()

    def enable_existing_output_toolbar_buttons(self, path_no_ext):
        number_of_tools = self.output_toolbar.GetToolsCount()
        for tool_num in range(number_of_tools):
            cur_tool = self.output_toolbar.GetToolByPos(tool_num)
            cur_id = cur_tool.GetId()
            if os.path.exists(path_no_ext + cur_tool.GetLabel()):
                self.output_toolbar.EnableTool(cur_id, True)
        self.output_toolbar.Realize()

    def get_current_selected_version(self):
        self.current_selected_version = None
        menu_list = self.option_version_menu.GetMenuItems()
        for menu_item in menu_list:
            if menu_item.IsChecked():
                self.current_selected_version = menu_item.GetLabel()
                break
        return self.current_selected_version

    def populate_help_menu(self):
        self.repopulate_help_menu()
        if self.current_workflow_directory:
            energyplus_application_directory, _ = os.path.split(self.current_workflow_directory)
            energyplus_documentation_directory = os.path.join(energyplus_application_directory, 'Documentation')
            if os.path.exists(energyplus_documentation_directory):
                documentation_files = os.listdir(energyplus_documentation_directory)
                for index, doc in enumerate(documentation_files):
                    specific_documentation_menu = self.help_menu.Insert(
                        index, 620 + index, doc, helpString=os.path.join(energyplus_documentation_directory, doc)
                    )
                    self.Bind(wx.EVT_MENU, self.handle_specific_documentation_menu, specific_documentation_menu)

    def repopulate_help_menu(self):
        menu_list = self.help_menu.GetMenuItems()
        for menu_item in menu_list:
            if not menu_item.IsSeparator():
                self.help_menu.Remove(menu_item)
            else:
                break
        # then build the items back up
        energyplus_application_directory, _ = os.path.split(self.current_workflow_directory)
        energyplus_documentation_directory = os.path.join(energyplus_application_directory, 'Documentation')
        if not os.path.exists(energyplus_documentation_directory):
            return
        documentation_files = os.listdir(energyplus_documentation_directory)
        for index, doc in enumerate(documentation_files):
            specific_documentation_menu = self.help_menu.Insert(
                index, 620 + index, doc, helpString=os.path.join(energyplus_documentation_directory, doc)
            )
            self.Bind(wx.EVT_MENU, self.handle_specific_documentation_menu, specific_documentation_menu)

    def run_workflow(self):
        if self.selected_directory and self.selected_file and self.current_workflow:
            for _, thread in self.workflow_threads.items():
                if thread.file_name == self.selected_file and thread.run_directory == self.selected_directory and thread.workflow_instance.name() == self.current_workflow.name:
                    self.show_error_message('ERROR: This workflow/dir/file combination is already running')
                    return
            new_uuid = str(uuid.uuid4())
            self.status_bar.SetStatusText('Starting workflow', i=0)
            new_instance = self.current_workflow.workflow_class()
            new_instance.register_standard_output_callback(
                new_uuid,
                self.callback_intermediary
            )
            self.workflow_threads[new_uuid] = WorkflowThread(
                new_uuid, self, new_instance, self.selected_directory, self.selected_file,
                {'weather': self.current_weather_file, 'workflow location': self.current_workflow.workflow_directory}
            )
            self.workflow_output_dialogs[new_uuid] = self.make_and_show_output_dialog(new_uuid)
            self.workflow_output_dialogs[new_uuid].update_output("*** STARTING WORKFLOW ***")
        else:
            self.show_error_message('ERROR: Make sure you select a workflow, directory and a file')
        self.update_num_processes_status()

    def make_and_show_output_dialog(self, workflow_id):
        max_dialog_vertical_increments = 5.0
        self.workflow_dialog_counter += 1
        if self.workflow_dialog_counter == max_dialog_vertical_increments:
            self.workflow_dialog_counter = 1

        this_workflow = self.workflow_threads[workflow_id]
        dlg = OutputDialog(None, title=this_workflow.workflow_instance.name())
        dlg.set_id(workflow_id)
        dlg.Bind(wx.EVT_CLOSE, self.output_dialog_closed)

        current_rectangle = self.GetRect()
        x_right_edge = current_rectangle[0] + current_rectangle[2]
        y_top = current_rectangle[1]
        vertical_increment = int(current_rectangle[3] / max_dialog_vertical_increments / 2.0)
        this_x = x_right_edge + 5
        this_y = y_top + vertical_increment * (self.workflow_dialog_counter - 1)
        dlg.set_x_y(this_x, this_y)

        dlg.set_config(
            json.dumps(
                {
                    'workflow_name:': self.workflow_threads[workflow_id].workflow_instance.name(),
                    'workflow_dir': self.workflow_threads[workflow_id].workflow_directory,
                    'file_name:': self.workflow_threads[workflow_id].file_name,
                    'run_directory:': self.workflow_threads[workflow_id].run_directory,
                },
                indent=2
            )
        )
        return dlg

    def output_dialog_closed(self, event):
        dialog = event.EventObject
        this_id = dialog.workflow_id
        dialog.Destroy()
        del self.workflow_output_dialogs[this_id]

    def enable_disable_idf_editor_button(self):
        file_name_no_ext, extension = os.path.splitext(self.selected_file)
        self.primary_toolbar.EnableTool(self.tb_idf_editor_id, extension.upper() == ".IDF")
        self.output_toolbar.Realize()

    def show_error_message(self, message):
        return wx.MessageBox(message, self.GetTitle() + ' Error', wx.OK | wx.ICON_ERROR)

    def show_yes_no_question(self, message):
        return wx.MessageBox(message, self.GetTitle() + ' Question', wx.YES_NO | wx.ICON_QUESTION)

    def any_threads_running(self):
        return len(self.workflow_threads) > 0

# GUI Building Functions

    def gui_build(self):

        self.gui_build_menu_bar()

        # build the left/right main splitter
        main_left_right_splitter = wx.SplitterWindow(self, wx.ID_ANY)

        # build tree view and add it to the left pane
        directory_tree_panel = wx.Panel(main_left_right_splitter, wx.ID_ANY)
        self.directory_tree_control = wx.GenericDirCtrl(directory_tree_panel, -1, style=wx.DIRCTRL_DIR_ONLY)
        tree = self.directory_tree_control.GetTreeCtrl()
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.handle_dir_selection_changed, tree)

        directory_tree_sizer = wx.BoxSizer(wx.VERTICAL)
        directory_tree_sizer.Add(self.directory_tree_control, 1, wx.EXPAND, 0)
        directory_tree_panel.SetSizer(directory_tree_sizer)

        # build list views and add to the right pane
        file_lists_panel = wx.Panel(main_left_right_splitter, wx.ID_ANY)
        self.file_lists_splitter = wx.SplitterWindow(file_lists_panel, wx.ID_ANY)

        # build control list view (top right)
        self.control_file_list_panel = wx.Panel(self.file_lists_splitter, wx.ID_ANY)
        self.control_file_list = wx.ListCtrl(self.control_file_list_panel, wx.ID_ANY,
                                             style=wx.LC_HRULES | wx.LC_REPORT | wx.LC_VRULES | wx.LC_SINGLE_SEL)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.handle_list_ctrl_selection, self.control_file_list)
        control_file_list_sizer = wx.BoxSizer(wx.VERTICAL)
        control_file_list_sizer.Add(self.control_file_list, 1, wx.EXPAND, 0)
        self.control_file_list_panel.SetSizer(control_file_list_sizer)

        # build raw list view (bottom right)
        self.raw_file_list_panel = wx.Panel(self.file_lists_splitter, wx.ID_ANY)
        self.raw_file_list = wx.ListCtrl(self.raw_file_list_panel, wx.ID_ANY,
                                         style=wx.LC_HRULES | wx.LC_REPORT | wx.LC_VRULES)
        raw_file_list_sizer = wx.BoxSizer(wx.VERTICAL)
        raw_file_list_sizer.Add(self.raw_file_list, 1, wx.EXPAND, 0)
        self.raw_file_list_panel.SetSizer(raw_file_list_sizer)

        # not sure why but it works better if you make the split and unsplit it right away
        self.file_lists_splitter.SetMinimumPaneSize(20)
        self.file_lists_splitter.SplitHorizontally(self.control_file_list_panel, self.raw_file_list_panel)
        self.file_lists_splitter.Unsplit(toRemove=self.raw_file_list_panel)

        sizer_right = wx.BoxSizer(wx.HORIZONTAL)
        sizer_right.Add(self.file_lists_splitter, 1, wx.EXPAND, 0)

        # add the entire right pane to the main left/right splitter
        file_lists_panel.SetSizer(sizer_right)
        main_left_right_splitter.SetMinimumPaneSize(20)
        main_left_right_splitter.SplitVertically(directory_tree_panel, file_lists_panel)

        # now set up the main frame's layout sizer
        main_app_vertical_sizer = wx.BoxSizer(wx.VERTICAL)
        self.gui_build_primary_toolbar()
        main_app_vertical_sizer.Add(self.primary_toolbar, 0, wx.EXPAND, 0)
        self.gui_build_output_toolbar()
        main_app_vertical_sizer.Add(self.output_toolbar, 0, wx.EXPAND, 0)
        main_app_vertical_sizer.Add(main_left_right_splitter, 1, wx.EXPAND, 0)

        # add the status bar
        self.status_bar = self.CreateStatusBar(3)

        # assign the final form's sizer
        self.SetSizer(main_app_vertical_sizer)
        main_app_vertical_sizer.Fit(self)

        # get the window size and position
        previous_height = self.config.ReadInt("/ActiveWindow/height")
        previous_height = max(previous_height, self.DefaultSize[1])
        previous_width = self.config.ReadInt("/ActiveWindow/width")
        previous_width = max(previous_width, self.DefaultSize[0])
        previous_x = self.config.ReadInt("/ActiveWindow/x")
        previous_x = max(previous_x, 128)
        previous_y = self.config.ReadInt("/ActiveWindow/y")
        previous_y = max(previous_y, 128)
        self.SetSize(previous_x, previous_y, previous_width, previous_height)

        # call this to finalize
        self.Layout()

    def gui_build_primary_toolbar(self):

        self.primary_toolbar = wx.ToolBar(self, style=wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT)

        t_size = (24, 24)
        self.primary_toolbar.SetToolBitmapSize(t_size)

        choice_strings = [w.description for w in self.work_flows]
        self.workflow_choice = wx.Choice(self.primary_toolbar, choices=choice_strings)

        # So, on my Mac, the workflow_choice went invisible when I left the AddControl call in there
        # There was space where it obviously went, but it was invisible
        # This needs to be remedied, big time, but until then, on this branch I am:
        #  - removing the call to AddControl, thus the dropdown will show up, but not be aligned properly, then
        #  -  making it really wide so that I can easily click it on the right half of the toolbar
        # if 'CHOICEWORKAROUND' in os.environ:
        if Platform.get_current_platform() == Platform.MAC:
            workflow_choice_size = (700, -1)
            self.workflow_choice = wx.Choice(self.primary_toolbar, choices=choice_strings, size=workflow_choice_size)
        else:
            self.primary_toolbar.AddControl(self.workflow_choice)

        self.primary_toolbar.Bind(wx.EVT_CHOICE, self.handle_choice_selection_change, self.workflow_choice)

        previous_workflow = self.config.Read('/ActiveWindow/SelectedWorkflow', defaultVal='')
        self.refresh_workflow_selection(previous_workflow)

        file_open_bmp = wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_TOOLBAR, t_size)
        tb_weather = self.primary_toolbar.AddTool(
            10, "Weather", file_open_bmp, wx.NullBitmap, wx.ITEM_NORMAL, "Weather", "Select a weather file", None
        )
        self.primary_toolbar.Bind(wx.EVT_TOOL, self.handle_tb_weather, tb_weather)

        forward_bmp = wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD, wx.ART_TOOLBAR, t_size)
        run_button_id = 20
        self.tb_run = self.primary_toolbar.AddTool(
            run_button_id, "Run", forward_bmp, wx.NullBitmap, wx.ITEM_NORMAL, "Run",
            "Run the selected workflow on the selected file", None
        )
        self.primary_toolbar.Bind(wx.EVT_TOOL, self.handle_tb_run, self.tb_run)

        self.primary_toolbar.AddSeparator()

        exe_bmp = wx.ArtProvider.GetBitmap(wx.ART_EXECUTABLE_FILE, wx.ART_TOOLBAR, t_size)
        self.tb_idf_editor_id = 40
        tb_idf_editor = self.primary_toolbar.AddTool(
            self.tb_idf_editor_id, "IDF Editor", exe_bmp, wx.NullBitmap, wx.ITEM_NORMAL, "IDF Editor",
            "Open the selected file using the IDF Editor", None
        )
        self.primary_toolbar.Bind(wx.EVT_TOOL, self.handle_tb_idf_editor, tb_idf_editor)

        tb_text_editor = self.primary_toolbar.AddTool(
            50, "Text Editor", exe_bmp, wx.NullBitmap, wx.ITEM_NORMAL, "Text Editor",
            "Open the selected file using the text editor", None
        )
        self.primary_toolbar.Bind(wx.EVT_TOOL, self.handle_tb_text_editor, tb_text_editor)

        self.primary_toolbar.AddSeparator()

        folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_TOOLBAR, t_size)
        tb_explorer = self.primary_toolbar.AddTool(
            80, "Explorer", folder_bmp, wx.NullBitmap, wx.ITEM_NORMAL, "Explorer",
            "Open the file explorer in the current directory", None
        )
        self.primary_toolbar.Bind(wx.EVT_TOOL, self.handle_tb_explorer, tb_explorer)

        remove_bmp = wx.ArtProvider.GetBitmap(wx.ART_MINUS, wx.ART_TOOLBAR, t_size)
        tb_hide_all_files_pane = self.primary_toolbar.AddTool(
            100, "All Files", remove_bmp, wx.NullBitmap, wx.ITEM_CHECK, "All Files",
            "Show the panel with all the files for the directory", None
        )
        self.primary_toolbar.Bind(wx.EVT_TOOL, self.handle_tb_hide_all_files_pane, tb_hide_all_files_pane)

        self.primary_toolbar.Realize()

    def gui_build_output_toolbar(self):
        self.output_toolbar_icon_size = (16, 15)
        self.output_toolbar = wx.ToolBar(self, style=wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT)
        self.output_toolbar.SetToolBitmapSize(self.output_toolbar_icon_size)
        wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_TOOLBAR, self.output_toolbar_icon_size)
        self.output_toolbar.Realize()

    def gui_build_menu_bar(self):

        self.menu_bar = wx.MenuBar()

        file_menu = wx.Menu()
        self.menu_file_run = file_menu.Append(10, "Run File", "Run currently selected file for selected workflow")
        self.Bind(wx.EVT_MENU, self.handle_menu_file_run, self.menu_file_run)
        menu_file_quit = file_menu.Append(wx.ID_EXIT, 'Quit', 'Quit application')
        self.Bind(wx.EVT_MENU, self.handle_menu_file_quit, menu_file_quit)
        self.menu_bar.Append(file_menu, '&File')

        self.folder_menu = wx.Menu()
        self.folder_menu.Append(301, "Recent", "Recently used folders.")
        self.folder_menu.Append(302, kind=wx.ITEM_SEPARATOR)
        self.folder_menu.Append(303, kind=wx.ITEM_SEPARATOR)
        self.folder_recent = FileNameMenus(self.folder_menu, 302, 303, self.config, "/FolderMenu/Recent")
        self.folder_recent.retrieve_config()
        for menu_item in self.folder_recent.menu_items_for_files:
            self.Bind(wx.EVT_MENU, self.handle_folder_recent_menu_selection, menu_item)

        self.folder_menu.Append(304, "Favorites", "Favorite folders.")
        self.folder_menu.Append(305, kind=wx.ITEM_SEPARATOR)
        self.folder_menu.Append(306, kind=wx.ITEM_SEPARATOR)
        self.folder_favorites = FileNameMenus(self.folder_menu, 305, 306, self.config, "/FolderMenu/Favorite")
        self.folder_favorites.retrieve_config()
        for menu_item in self.folder_favorites.menu_items_for_files:
            self.Bind(wx.EVT_MENU, self.handle_folder_favorites_menu_selection, menu_item)

        add_current_folder_to_favorites = self.folder_menu.Append(
            307, "Add Current Folder to Favorites", "Add Current Folder to Favorites"
        )
        self.Bind(wx.EVT_MENU, self.handle_add_current_folder_to_favorites_menu_selection,
                  add_current_folder_to_favorites)
        remove_current_folder_from_favorites = self.folder_menu.Append(
            308, "Remove Current Folder from Favorites", "Remove Current Folder from Favorites"
        )
        self.Bind(wx.EVT_MENU, self.handle_remove_current_folder_from_favorites_menu_selection,
                  remove_current_folder_from_favorites)
        self.menu_bar.Append(self.folder_menu, "F&older")
        # disable the menu items that are just information
        self.menu_bar.Enable(301, False)
        self.menu_bar.Enable(304, False)

        self.weather_menu = wx.Menu()
        menu_weather_select = self.weather_menu.Append(401, "Select..", "Select a weather file")
        self.Bind(wx.EVT_MENU, self.handle_menu_weather_select, menu_weather_select)
        self.weather_menu.Append(402, kind=wx.ITEM_SEPARATOR)
        self.weather_menu.Append(403, "Recent", "Recently selected weather files.")
        self.weather_menu.Append(404, kind=wx.ITEM_SEPARATOR)
        self.weather_menu.Append(405, kind=wx.ITEM_SEPARATOR)
        self.weather_recent = FileNameMenus(self.weather_menu, 404, 405, self.config, "/WeatherMenu/Recent")
        self.weather_recent.retrieve_config()
        for menu_item in self.weather_recent.menu_items_for_files:
            self.Bind(wx.EVT_MENU, self.handle_weather_recent_menu_selection, menu_item)

        self.weather_menu.Append(406, "Favorites", "Favorite weather files")
        self.weather_menu.Append(407, kind=wx.ITEM_SEPARATOR)
        self.weather_menu.Append(408, kind=wx.ITEM_SEPARATOR)
        add_current_weather_to_favorites = self.weather_menu.Append(
            409, "Add Weather to Favorites", "Add Weather to Favorites"
        )
        self.Bind(wx.EVT_MENU, self.handle_add_current_weather_to_favorites_menu_selection,
                  add_current_weather_to_favorites)
        remove_current_weather_from_favorites = self.weather_menu.Append(
            410, "Remove Weather from Favorites", "Remove Weather from Favorites"
        )
        self.Bind(wx.EVT_MENU, self.handle_remove_current_weather_from_favorites_menu_selection,
                  remove_current_weather_from_favorites)
        self.weather_favorites = FileNameMenus(self.weather_menu, 407, 408, self.config, "/WeatherMenu/Favorite")
        self.weather_favorites.retrieve_config()
        for menu_item in self.weather_favorites.menu_items_for_files:
            self.Bind(wx.EVT_MENU, self.handle_weather_favorites_menu_selection, menu_item)

        self.menu_bar.Append(self.weather_menu, "&Weather")
        # disable the menu items that are just information
        self.menu_bar.Enable(403, False)
        self.menu_bar.Enable(406, False)

        self.output_menu = wx.Menu()
        self.menu_bar.Append(self.output_menu, "&Output")

        options_menu = wx.Menu()
        self.option_version_menu = wx.Menu()
        for index, version_info in enumerate(self.list_of_versions):
            version_string = version_info['version']
            specific_version_menu = self.option_version_menu.Append(710 + index, version_string, kind=wx.ITEM_RADIO)
            self.Bind(wx.EVT_MENU, self.handle_specific_version_menu, specific_version_menu)
        options_menu.Append(71, "Version", self.option_version_menu)
        self.retrieve_selected_version_config()
        menu_option_workflow_directories = options_menu.Append(
            72, "Workflow Directories...", 'Select directories where workflows are located'
        )
        self.Bind(wx.EVT_MENU, self.handle_menu_option_workflow_directories, menu_option_workflow_directories)

        self.menu_output_toolbar = options_menu.Append(761, "<workspacename> Output Toolbar...")
        self.Bind(wx.EVT_MENU, self.handle_menu_output_toolbar, self.menu_output_toolbar)
        self.menu_bar.Append(options_menu, "&Settings")

        self.help_menu = wx.Menu()
        self.help_menu.AppendSeparator()
        menu_help_about = self.help_menu.Append(615, "About EP-Launch")
        self.Bind(wx.EVT_MENU, self.handle_menu_help_about, menu_help_about)
        self.current_selected_version = self.get_current_selected_version()
        self.current_workflow_directory = self.locate_workflows.get_workflow_directory(
            self.current_selected_version
        )
        self.repopulate_help_menu()
        self.menu_bar.Append(self.help_menu, "&Help")

        self.SetMenuBar(self.menu_bar)

# Event Handling Functions

    @staticmethod
    def callback_intermediary(workflow_id, message):
        wx.CallAfter(pub.sendMessage, "workflow_callback", workflow_id=workflow_id, message=message)

    def workflow_callback(self, workflow_id, message):
        if workflow_id in self.workflow_output_dialogs:
            self.workflow_output_dialogs[workflow_id].update_output(message)

    def handle_frame_close(self, event):
        if self.any_threads_running():
            msg = 'Program closing, but there are threads running; would you like to kill the threads and close?'
            response = self.show_yes_no_question(msg)
            if response == wx.YES:
                for thread_id in self.workflow_threads:
                    try:
                        self.workflow_threads[thread_id].abort()
                        self.workflow_output_dialogs[thread_id].Close()
                    except Exception as e:
                        print("Tried to abort thread, but something went awry: " + str(e))
            elif response == wx.NO:
                event.Veto()
                return
        self.save_config()
        self.Destroy()

    def handle_out_tb_button(self, event):
        full_path_name = os.path.join(self.selected_directory, self.selected_file)
        tb_button = self.output_toolbar.FindById(event.GetId())
        output_file_name = self.file_name_manipulator.replace_extension_with_suffix(full_path_name, tb_button.Label)
        self.external_runner.run_program_by_extension(output_file_name)

    def handle_list_ctrl_selection(self, event):
        self.selected_file = event.Item.Text
        self.update_output_file_status()
        self.enable_disable_idf_editor_button()

    def handle_menu_file_run(self, event):
        self.folder_recent.add_recent(self.directory_tree_control.GetPath())
        self.run_workflow()

    def handle_menu_file_quit(self, event):
        self.Close()

    def handle_tb_run(self, event):
        if not self.current_workflow or not self.selected_file or not self.selected_directory:
            return  # error
        self.folder_recent.add_recent(self.directory_tree_control.GetPath())
        if not self.current_weather_file:
            self.current_weather_file = ''
        self.current_cache.add_config(
            self.current_workflow.name,
            self.selected_file,
            {'weather': self.current_weather_file}
        )
        self.current_cache.write()
        self.run_workflow()
        self.update_output_file_status()

    def handle_workflow_done(self, event):
        status_message = 'Invalid workflow response'
        try:
            successful = event.data.success
            if successful:
                status_message = 'Successfully completed a workflow: ' + event.data.message
                try:
                    data_from_workflow = event.data.column_data
                    workflow_working_directory = self.workflow_threads[event.data.id].run_directory
                    workflow_directory_cache = CacheFile(workflow_working_directory)
                    # TODO: What if workflows change while a workflow is running...we shouldn't allow that
                    workflow_directory_cache.add_result(
                        self.workflow_threads[event.data.id].workflow_instance.name(),
                        self.workflow_threads[event.data.id].file_name,
                        data_from_workflow
                    )
                    if self.selected_directory == workflow_working_directory:
                        # only update file lists if we are still in that directory
                        self.update_file_lists()
                except EPLaunchFileException:
                    pass
                self.workflow_output_dialogs[event.data.id].Close()
            else:
                status_message = 'Workflow failed: ' + event.data.message
                self.workflow_output_dialogs[event.data.id].update_output('Workflow FAILED: ' + event.data.message)
                self.workflow_output_dialogs[event.data.id].update_output("*** WORKFLOW FINISHED ***")
        except Exception as e:  # noqa -- there is *no* telling what all exceptions could occur inside a workflow
            print(e)
            status_message = 'Workflow response was invalid'
        self.status_bar.SetStatusText(status_message, i=0)
        try:
            del self.workflow_threads[event.data.id]
        except Exception as e:
            print(e)
        self.update_num_processes_status()

    def handle_dir_selection_changed(self, event):
        self.selected_directory = self.directory_tree_control.GetPath()
        # manage the check marks when changing directories
        self.folder_recent.uncheck_all()
        self.folder_recent.put_checkmark_on_item(self.selected_directory)
        self.folder_favorites.uncheck_all()
        self.folder_favorites.put_checkmark_on_item(self.selected_directory)
        self.current_cache = CacheFile(self.selected_directory)
        try:
            self.status_bar.SetStatusText('Selected directory: ' + self.selected_directory, i=0)
            self.update_file_lists()
        except Exception as e:  # noqa -- status_bar and things may not exist during initialization, just ignore
            print(e)
            pass
        event.Skip()

    def handle_choice_selection_change(self, event):
        self.current_workflow = self.work_flows[event.Selection]
        self.update_control_list_columns()
        self.update_file_lists()
        self.update_workflow_dependent_menu_items()
        self.status_bar.SetStatusText('Choice selection changed to ' + event.String, i=0)

    def handle_tb_weather(self, event):
        filename = wx.FileSelector("Select a weather file", wildcard="EnergyPlus Weather File(*.epw)|*.epw",
                                   flags=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        self.current_weather_file = filename
        self.weather_recent.uncheck_all()
        self.weather_recent.add_recent(filename)
        self.weather_favorites.uncheck_all()
        self.weather_favorites.put_checkmark_on_item(filename)
        self.status_bar.SetStatusText('Weather: ' + self.current_weather_file, i=1)

    def handle_tb_hide_all_files_pane(self, event):
        # the following remove the top pane of the right hand splitter
        if self.file_lists_splitter.IsSplit():
            self.file_lists_splitter.Unsplit(toRemove=self.raw_file_list_panel)
        else:
            self.file_lists_splitter.SplitHorizontally(self.control_file_list_panel, self.raw_file_list_panel)

    def handle_menu_option_workflow_directories(self, event):
        workflow_dir_dialog = workflow_directories_dialog.WorkflowDirectoriesDialog(None, title='Workflow Directories')
        workflow_dir_dialog.set_listbox(self.workflow_directories)
        return_value = workflow_dir_dialog.ShowModal()
        if return_value == wx.ID_OK:
            self.workflow_directories = workflow_dir_dialog.list_of_directories
            print(self.workflow_directories)
        # May need to refresh the main UI if something changed in the settings
        workflow_dir_dialog.Destroy()

    def handle_menu_output_toolbar(self, event):

        if not self.current_workflow:
            return

        output_suffixes = self.current_workflow.get_output_suffixes()

        if self.current_workflow.output_toolbar_order is None:
            order = []
            for count, suffix in enumerate(output_suffixes):
                if count < 15:
                    order.append(count)
                else:
                    order.append(-count)
        else:
            order = self.current_workflow.output_toolbar_order

        dlg = wx.RearrangeDialog(None,
                                 "Arrange the buttons on the output toolbar",
                                 "{} Output Toolbar".format(self.current_workflow.name),
                                 order, output_suffixes)

        if dlg.ShowModal() == wx.ID_OK:
            order = dlg.GetOrder()
            print(order)
            self.current_workflow.output_toolbar_order = order
            self.update_output_toolbar()

    def handle_menu_weather_select(self, event):
        filename = wx.FileSelector("Select a weather file", wildcard="EnergyPlus Weather File(*.epw)|*.epw",
                                   flags=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        self.current_weather_file = filename
        self.weather_recent.uncheck_all()
        self.weather_recent.add_recent(filename)
        self.weather_favorites.uncheck_all()
        self.weather_favorites.put_checkmark_on_item(filename)
        self.status_bar.SetStatusText('Weather: ' + self.current_weather_file, i=1)

    def handle_folder_recent_menu_selection(self, event):
        menu_item = self.folder_menu.FindItemById(event.GetId())
        print('from frame.py - folder recent clicked menu item:', menu_item.GetLabel(), menu_item.GetId())
        self.folder_recent.uncheck_other_items(menu_item)
        real_path = os.path.abspath(menu_item.GetLabel())
        self.directory_tree_control.SelectPath(real_path, True)
        self.directory_tree_control.ExpandPath(real_path)

    def handle_folder_favorites_menu_selection(self, event):
        menu_item = self.folder_menu.FindItemById(event.GetId())
        print('from frame.py - folder favorites clicked menu item:', menu_item.GetLabel(), menu_item.GetId())
        self.folder_favorites.uncheck_other_items(menu_item)
        real_path = os.path.abspath(menu_item.GetLabel())
        self.directory_tree_control.SelectPath(real_path, True)
        self.directory_tree_control.ExpandPath(real_path)

    def handle_add_current_folder_to_favorites_menu_selection(self, event):
        self.folder_favorites.add_favorite(self.directory_tree_control.GetPath())

    def handle_remove_current_folder_from_favorites_menu_selection(self, event):
        self.folder_favorites.remove_favorite(self.directory_tree_control.GetPath())

    def handle_weather_recent_menu_selection(self, event):
        menu_item = self.weather_menu.FindItemById(event.GetId())
        self.current_weather_file = menu_item.GetLabel()
        self.weather_recent.uncheck_all()
        self.weather_recent.put_checkmark_on_item(self.current_weather_file)
        self.weather_favorites.uncheck_all()
        self.weather_favorites.put_checkmark_on_item(self.current_weather_file)
        self.status_bar.SetStatusText('Weather: ' + self.current_weather_file, i=1)

    def handle_weather_favorites_menu_selection(self, event):
        menu_item = self.weather_menu.FindItemById(event.GetId())
        self.current_weather_file = menu_item.GetLabel()
        self.weather_recent.uncheck_all()
        self.weather_recent.put_checkmark_on_item(self.current_weather_file)
        self.weather_favorites.uncheck_all()
        self.weather_favorites.put_checkmark_on_item(self.current_weather_file)
        self.status_bar.SetStatusText('Weather: ' + self.current_weather_file, i=1)

    def handle_add_current_weather_to_favorites_menu_selection(self, event):
        self.weather_favorites.add_favorite(self.current_weather_file)

    def handle_remove_current_weather_from_favorites_menu_selection(self, event):
        self.weather_favorites.remove_favorite(self.current_weather_file)

    def handle_tb_idf_editor(self, event):
        full_path_name = os.path.join(self.selected_directory, self.selected_file)
        self.external_runner.run_idf_editor(full_path_name)

    def handle_tb_text_editor(self, event):
        full_path_name = os.path.join(self.selected_directory, self.selected_file)
        self.external_runner.run_text_editor(full_path_name)

    def handle_output_menu_item(self, event):
        full_path_name = os.path.join(self.selected_directory, self.selected_file)
        menu_item = self.output_menu.FindItemById(event.GetId())
        output_file_name = self.file_name_manipulator.replace_extension_with_suffix(full_path_name,
                                                                                    menu_item.GetLabel())
        self.external_runner.run_program_by_extension(output_file_name)

    def handle_extra_output_menu_item(self, event):
        full_path_name = os.path.join(self.selected_directory, self.selected_file)
        menu_item = self.extra_output_menu.FindItemById(event.GetId())
        output_file_name = self.file_name_manipulator.replace_extension_with_suffix(full_path_name,
                                                                                    menu_item.GetLabel())
        self.external_runner.run_program_by_extension(output_file_name)

    def handle_specific_version_menu(self, event):
        self.current_selected_version = self.get_current_selected_version()
        for eplus_dir in self.energyplus_workflow_directories:
            formatted_dir = eplus_dir.upper().replace('-', '.')
            if self.current_selected_version.upper() in formatted_dir:
                self.current_workflow_directory = eplus_dir
                break
        self.update_workflow_list(self.current_selected_version)
        self.workflow_choice.Clear()
        for work_flow in self.work_flows:
            self.workflow_choice.Append(work_flow.description)
        self.repopulate_help_menu()

    def handle_specific_documentation_menu(self, event):
        menu_item = self.help_menu.FindItemById(event.GetId())
        documentation_item_full_path = menu_item.GetHelp()
        self.external_runner.run_program_by_extension(documentation_item_full_path)

    def handle_tb_explorer(self, event):
        current_platform = Platform.get_current_platform()
        if current_platform == Platform.WINDOWS:  # pragma: no cover
            os.system('start {}'.format(self.selected_directory))
        elif current_platform == Platform.LINUX:
            os.system('xdg-open "{}"'.format(self.selected_directory))
        elif current_platform == Platform.MAC:  # pragma: no cover
            os.system('open "{}"'.format(self.selected_directory))
        else:
            pass

    def handle_menu_help_about(self, event):
        text = """
EP-Launch
               
Version 0.9
Copyright (c) 2018, Alliance for Sustainable Energy, LLC  and GARD Analytics, Inc

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
 list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
this list of conditions and the following disclaimer in the documentation
and/or other materials provided with the distribution.

* The name of the copyright holder(s), any contributors, the United States
Government, the United States Department of Energy, or any of their employees
may not be used to endorse or promote products derived from this software
without specific prior written permission from the respective party.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER(S) AND ANY CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR 
PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER(S), ANY , 
CONTRIBUTORS THE UNITED STATES GOVERNMENT, OR THE UNITED STATES DEPARTMENT  
OF ENERGY, NOR ANY OF THEIR EMPLOYEES, BE LIABLE FOR ANY DIRECT, INDIRECT, 
INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT  
NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, 
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY 
OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING 
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
        with wx.MessageDialog(self, text, 'About EP-Launch', wx.OK | wx.ICON_INFORMATION) as dlg:
            dlg.ShowModal()

# Retrieve Config Functions

    def retrieve_workflow_directories_config(self):
        count_directories = self.config.ReadInt("/WorkflowDirectories/Count", 0)
        list_of_directories = []
        for count in range(0, count_directories):
            directory = self.config.Read("/WorkflowDirectories/Path-{:02d}".format(count))
            if directory:
                if os.path.exists(directory):
                    list_of_directories.append(directory)
        self.workflow_directories = list_of_directories

    def retrieve_selected_version_config(self):
        possible_selected_version = self.config.Read("/ActiveWindow/CurrentVersion")
        menu_list = self.option_version_menu.GetMenuItems()
        if not possible_selected_version and len(menu_list) >= 1:
            count = -1
            for menu_item in menu_list:
                count = count + 1
            menu_list[count].Check(True)
        else:
            for menu_item in menu_list:
                if menu_item.GetLabel() == possible_selected_version:
                    menu_item.Check(True)
                    break

    def retrieve_current_directory_config(self):
        possible_directory_name = self.config.Read("/ActiveWindow/CurrentDirectory")
        # set the default to the ExampleFiles directory
        if not possible_directory_name:
            current_energyplus_directory, _ = os.path.split(self.current_workflow_directory)
            possible_directory_name = os.path.join(current_energyplus_directory, 'ExampleFiles')
        if possible_directory_name:
            self.selected_directory = possible_directory_name
            real_path = os.path.abspath(self.selected_directory)
            self.directory_tree_control.SelectPath(real_path, True)
            self.directory_tree_control.ExpandPath(real_path)

# Save Config Functions

    def save_config(self):
        self.folder_favorites.save_config()
        self.folder_recent.save_config()
        self.weather_favorites.save_config()
        self.weather_recent.save_config()
        self.save_workflow_directories_config()
        self.save_current_directory_config()
        self.save_selected_workflow_config()
        self.save_window_size()
        self.save_selected_version_config()

    def save_current_directory_config(self):
        if self.selected_directory:
            self.config.Write("/ActiveWindow/CurrentDirectory", self.selected_directory)
        if self.selected_file:
            self.config.Write("/ActiveWindow/CurrentFileName", self.selected_file)

    def save_selected_workflow_config(self):
        if self.current_workflow:
            self.config.Write("/ActiveWindow/SelectedWorkflow", self.current_workflow.name)

    def save_window_size(self):
        current_size = self.GetSize()
        self.config.WriteInt("/ActiveWindow/height", current_size.height)
        self.config.WriteInt("/ActiveWindow/width", current_size.width)
        current_position = self.GetPosition()
        self.config.WriteInt("/ActiveWindow/x", current_position.x)
        self.config.WriteInt("/ActiveWindow/y", current_position.y)

    def save_selected_version_config(self):
        self.get_current_selected_version()
        if self.current_selected_version:
            self.config.Write("/ActiveWindow/CurrentVersion", self.current_selected_version)

    def save_workflow_directories_config(self):
        # in Windows using RegEdit these appear in:
        #    HKEY_CURRENT_USER\Software\EP-Launch3
        self.config.WriteInt("/WorkflowDirectories/Count", len(self.workflow_directories))
        # save menu items to configuration file
        for count, workflow_directory in enumerate(self.workflow_directories):
            self.config.Write("/WorkflowDirectories/Path-{:02d}".format(count), workflow_directory)
