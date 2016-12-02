import sublime, sublime_plugin, traceback
import json, threading, time, sys, os, time, subprocess
from types import *
from .interop import *
from .msg_parser import *
from .fuse_parseutils import *
from .fuse_util import *
from .go_to_definition import *
from .version import VERSION
from .log import log
from .building import BuildManager
from . import build_results

gFuse = None

class Fuse():
	items = []
	isUpdatingCache = False
	interop = None
	useShortCompletion = False
	wordAtCaret = ""
	doCompleteAttribs = False
	foldUXNameSpaces = False
	completionSyntax = None
	msgManager = MsgManager()
	startFuseThread = None
	startFuseThreadExit = False
	startFuseEvent = threading.Event()
	previousBuildCommand = None

	def __init__(self):
		self.interop = Interop(self.recv, self.onConnected, self.tryConnect)
		self.startFuseThread = threading.Thread(target = self.tryConnectThread)
		self.startFuseThread.daemon = True
		self.startFuseThread.start()
		self.buildManager = BuildManager(self.showFuseNotFound)

	#TODO make module
	def publishFocusEditorService(self):
		self.msgManager.sendRequestAsync(
			self.interop,
			"PublishService",
			{
				"RequestNames" : ["FocusEditor"]
			},
			self.focusEditorServiceSuccess)

	def focusEditorServiceSuccess(self, _):
		log().info("Successfully registered FocusEditor service")

	def recv(self, msg):
		try:
			parsedRes = self.msgManager.parse(msg)

			if parsedRes == None:
				return

			if parsedRes.messageType == "Event":
				build_results.tryHandleBuildEvent(parsedRes)
			elif parsedRes.messageType == "Request":
				self.handleRequest(parsedRes)

		except:
			log().error(traceback.format_exc())

	def handleRequest(self, request):
		if request.name == "FocusEditor":
			if self.tryHandleFocusRequest(request):
				return
		self.msgManager.sendResponse(self.interop, request.id, "Unhandled")

	def tryHandleFocusRequest(self, request):
		if self.projectIsOpen(request.arguments["Project"]):
			window = sublime.active_window()
			view = window.open_file(
				"{}:{}:{}".format(*[request.arguments[field] for field in ("File", "Line", "Column")]),
				sublime.ENCODED_POSITION)
			if sublime.platform() == "osx":
				self.focusWindowOSX()
				self.msgManager.sendResponse(self.interop, request.id, "Success")
				return True
			elif sublime.platform() == "windows":
				self.msgManager.sendResponse(self.interop, request.id, "Success", {"FocusHwnd":window.hwnd()})
				return True
		return False

	def projectIsOpen(self, project):
		if not os.path.isfile(project):
			return False
		for folder in sublime.active_window().folders():
			if project.startswith(folder):
				return True
		return False

	def focusWindowOSX(self):
		cmd = """
			tell application "System Events"
				activate application "Sublime Text"
			end tell"""
		subprocess.Popen(['/usr/bin/osascript', "-e", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

	def showFuseNotFound(self):
		error_message("Fuse could not be found.\n\nAttempted to run from: '"+getFusePathFromSettings()+"'\n\nPlease verify your Fuse installation." + self.rebootMessage())

	def rebootMessage(self):
		if str(sublime.platform()) == "windows":
			return " If this is the first time you are running Fuse, please try to restart your computer."
		return ""

	def handleCodeSuggestion(self, cmd):
		suggestions = cmd["CodeSuggestions"]

		self.isUpdatingCache = cmd["IsUpdatingCache"]
		self.items = []

		try:
			suggestedUXNameSpaces = []

			for suggestion in suggestions:

				outText = suggestionText = suggestion["Suggestion"]
				suggestionType = suggestion["Type"]
				hintText = "" # The right-column hint text

				if self.completionSyntax == "UX" and self.doCompleteAttribs and suggestionType == "Property":
					s = parseUXSuggestion(self.wordAtCaret, suggestion, suggestedUXNameSpaces, self.useShortCompletion, self.foldUXNameSpaces)
					if(s == None):
						continue
					else:
						outText = s[0]
						suggestionText = s[0]+s[1]					
				else:
					hintText = suggestion["ReturnType"]

					if suggestionType == "Method" or suggestionType == "Constructor":
						# Build sublime tab completion, type hint and verbose type hint
						parsedMethod = parseMethod(suggestion["AccessModifiers"], suggestionText, suggestion["MethodArguments"], hintText, suggestionType == "Constructor")

						if not self.useShortCompletion:
							suggestionText = parsedMethod[0]
						hintText = parsedMethod[1]

					if suggestionType == "Field" or suggestionType == "Property":
						hintText = trimType(hintText)


				if suggestion["PreText"] != "":
					suggestionText = suggestion["PreText"] + suggestion["PostText"]


				outText += "\t" + hintText
				if self.completionSyntax == "Uno":
					if self.wordAtCaret == "." or outText.casefold().find(self.wordAtCaret.casefold()) > -1:
						self.items.append((outText, suggestionText))
				else:
					self.items.append((outText, suggestionText))

		except:
			log().error(traceback.format_exc())

	lastResponse = None

	def onQueryCompletion(self, view):
		if getSetting("fuse_completion") == False:
		 	return

		syntaxName = getExtension(view.settings().get("syntax"))
		if not isSupportedSyntax(syntaxName):
		 	return

		self.doCompleteAttribs = getSetting("fuse_ux_attrib_completion")
		self.foldUXNameSpaces = getSetting("fuse_ux_attrib_folding")
		self.completionSyntax = syntaxName

		if self.lastResponse is None:
			self.requestAutoComplete(view, syntaxName, lambda res: self.responseAutoComplete(view, res))
			return ([("", "")], sublime.INHIBIT_WORD_COMPLETIONS)

		response = self.lastResponse
		self.lastResponse = None

		if response.status != "Success":
		 	return

		caret = view.sel()[0].a
		vstr = view.substr(caret)
		self.wordAtCaret = view.substr(view.word(caret)).strip()

		if vstr == "(" or vstr == "=" or vstr == "\"": 
			self.useShortCompletion = True
		else:
			self.useShortCompletion = False

		self.handleCodeSuggestion(response.data)
		
		data = (self.items, sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)
		if len(self.items) == 0:
		 	if self.isUpdatingCache == True:
		 		return ([("Updating suggestion cache...", "_"), ("", "")], sublime.INHIBIT_WORD_COMPLETIONS)

		 	if getSetting("fuse_if_no_completion_use_sublime") == False:				
		 		return ([("", "")], sublime.INHIBIT_WORD_COMPLETIONS)
		 	else:
		 		return

		self.items = []
		return data

	def responseAutoComplete(self, view, res):
		self.lastResponse = res
		view.run_command("auto_complete",
		{
            "disable_auto_insert": True,
            "api_completions_only": False,
            "next_completion_if_showing": False,
            "auto_complete_commit_on_tab": True,
        })

	def requestAutoComplete(self, view, syntaxName, callback):
		fileName = view.file_name()
		text = view.substr(sublime.Region(0,view.size()))
		caret = view.sel()[0].a

		self.msgManager.sendRequestAsync(
			self.interop,
			"Fuse.GetCodeSuggestions",
			{
				"Path": fileName, 
				"Text": text, 
				"SyntaxType": syntaxName, 
				"CaretPosition": getRowCol(view, caret)
			},
			callback)

	def onConnected(self):
		self.sendHello()
		self.publishFocusEditorService()

	def sendHello(self):
		log().info("Sending hello request")
		self.msgManager.sendRequest(self.interop, 
		"Hello",
		{
			"Identifier": "Sublime Text 3",					
			"EventFilter": ""
		})

	fuseStartedCallback = None

	def tryConnect(self, callback = None):
		self.fuseStartedCallback = callback
		self.startFuseEvent.set()

	def tryConnectThread(self):
		while not self.startFuseThreadExit:
			try:				
				self.startFuseEvent.wait()
				self.startFuseEvent.clear()
					
				if getSetting("fuse_enabled") == True and not self.interop.isConnected():

					path = getFusePathFromSettings()

					try:		
						start_daemon = [path, "daemon", "-b"]
						log().info("Calling subprocess '%s'", str(start_daemon))
						if os.name == "nt":
							CREATE_NO_WINDOW = 0x08000000			
							subprocess.check_output(start_daemon, creationflags=CREATE_NO_WINDOW, stderr=subprocess.STDOUT)
						else:
							subprocess.check_output(start_daemon, stderr=subprocess.STDOUT)
					except subprocess.CalledProcessError as e:
						log().error("Fuse returned exit status " + str(e.returncode) + ". Output was '" + e.output.decode("utf-8") + "'.")
						error_message("Error starting Fuse:\n\n" + e.output.decode("utf-8"))
						return
					except:
						log().error("Fuse not found: " + traceback.format_exc())
						gFuse.showFuseNotFound()
						return

					self.interop.connect()
					if self.fuseStartedCallback is not None:
						self.fuseStartedCallback()				
			except:
				log().error(traceback.format_exc())

	def cleanup(self):
		self.interop.disconnect()
		self.startFuseThreadExit = True
		self.startFuseEvent.set()

def plugin_loaded():
	log().info("Loading plugin")
	log().info("Sublime version '" + sublime.version() + "'")
	log().info("Fuse plugin version '" + VERSION + "'")
	global gFuse
	gFuse = Fuse()
	fix_osx_path()

	s = sublime.load_settings("Preferences.sublime-settings")
	if getSetting("fuse_open_files_in_same_window"):
		s.set("open_files_in_new_window", False)
	else:
		s.set("open_files_in_new_window", True)

	if getSetting("fuse_show_user_guide_on_start", True):
		sublime.active_window().run_command("open_file", {"file":"${packages}/Fuse/UserGuide.txt"})
		setSetting("fuse_show_user_guide_on_start", False)
	log().info("Plugin loaded successfully")

def fix_osx_path():
	if str(sublime.platform()) == "osx":
		capitan_path="/usr/local/bin"
		if not capitan_path in os.environ["PATH"]:
			os.environ["PATH"] += ":" + capitan_path

def plugin_unloaded():
	log().info("Unloading plugin")
	global gFuse
	if gFuse != None:
		gFuse.cleanup()
	gFuse = None
	log().info("Unloaded plugin")

class FuseEventListener(sublime_plugin.EventListener):
	lastCaret = -1

	def on_selection_modified_async(self, view):
		syntaxName = getExtension(view.settings().get("syntax"))
		if not syntaxName == "UX" or not getSetting("fuse_selection_enabled"):
		 	return

		# This is a race condition but it does not matter
		caret = view.sel()[0].a
		if caret == self.lastCaret:
			return
		self.lastCaret = caret

		fileName = view.file_name()
		text = view.substr(sublime.Region(0,view.size()))		

		gFuse.msgManager.sendEvent(gFuse.interop, "Fuse.Preview.SelectionChanged", 
		{
			"Path": fileName,
			"Text": text,
			"CaretPosition": getRowCol(view, caret)
		})

	def on_activated_async(self, view):
		syntaxName = getExtension(view.settings().get("syntax"))
		if not isSupportedSyntax(syntaxName):
			return
		gFuse.tryConnect();

	def on_query_completions(self, view, prefix, locations):
		return gFuse.onQueryCompletion(view)

class GotoDefinitionCommand(sublime_plugin.TextCommand):
	def run(self, edit):		
		view = self.view
		syntaxName = getExtension(view.settings().get("syntax"))		
		log().info("Requested goto definition for syntax type '%s'", syntaxName)
		if not isSupportedSyntax(syntaxName) or len(view.sel()) == 0:
			return

		text = view.substr(sublime.Region(0,view.size()))
		caret = view.sel()[0].a

		log().info("Requested goto definition for '%s': '%s'", view.file_name(), getRowCol(view, caret))

		response = gFuse.msgManager.sendRequest(
			gFuse.interop,
			"Fuse.GotoDefinition",
			{
				"Path": view.file_name(),
				"Text": text,
				"SyntaxType": syntaxName,
				"CaretPosition": getRowCol(view, caret),					
			}
		)

		if response == None:
			log().info("No response for goto definition")
			return

		if response.status != "Success":
			log().error("Error in goto definition: '%s'", response.status)
			return

		gotoDefinition(response.data)

class FuseBuild(sublime_plugin.WindowCommand):
	def run(self, working_dir, build_target, run, paths=[]):
		log().info("Requested build: platform:'%s', build_target:'%s', working_dir:'%s'", str(sublime.platform()), build_target, working_dir)
		gFuse.tryConnect()
		working_dir = working_dir or os.path.dirname(paths[0])
		gFuse.buildManager.build(build_target, run, working_dir, error_message)

class FuseCreate(sublime_plugin.WindowCommand):
	targetFolder = ""
	targetTemplate = ""

	def run(self, type, paths = []):
		self.targetTemplate = type
		folders = self.window.folders()
		if len(paths) == 0:
			if len(folders) == 0:
				return
			else:
				self.targetFolder = folders[0]
		else:
			for path in paths:
				self.targetFolder = ""
				# File or folder?
				if os.path.isfile(path):
					self.targetFolder = os.path.dirname(path)
				else:
					self.targetFolder = path


		header = "";
		if type=="app":
			header = "Choose a project name:"
		elif type=="uno":
			header = "Choose a class name:"
		else:
			header = "Choose a file name:"

		self.window.show_input_panel(header, "", self.on_done, None, None)

	def on_done(self, file_name):
		try:
			log().info("Trying to create '" + self.full_path(file_name) +  "'")
			args = [getFusePathFromSettings(), "create", self.targetTemplate, file_name, self.targetFolder]
			try:
				proc = subprocess.Popen(args, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			except:
				gFuse.showFuseNotFound()
				return
			code = proc.wait()
			if code == 0:
				log().info("Succssfully created '" + self.full_path(file_name) +  "'")
				if self.targetTemplate != "app":
					self.window.open_file(self.full_path(file_name));
			else:
				out = "Could not create file:\n";
				out += self.full_path(file_name) + "\n";
				for line in proc.stdout.readlines():
					out += line.decode()
				error_message(out)
		except ValueError:
			pass

	def is_enabled(self, type, paths = []):
		return True

	def full_path(self, file_name):
	    return os.path.join(self.targetFolder, file_name) + "." + self.targetTemplate

class FuseOpenUrl(sublime_plugin.ApplicationCommand):
	def run(self, url):
		if sys.platform=='win32':
			os.startfile(url)
		elif sys.platform=='darwin':
			subprocess.Popen(['open', url])

class FusePreview(sublime_plugin.ApplicationCommand):
	def run(self, type, paths = []):	
		log().info("Starting preview for %s", str(paths))
		gFuse.tryConnect()
		for path in paths:
			gFuse.buildManager.preview(type, path)

	def is_visible(self, type, paths = []):
		if os.name == "nt" and type == "iOS":
			return False
		return True

	def is_enabled(self, type, paths = []):
		for path in paths:
			if contains_unoproj(path):
				return True
			if path == None:
				return False
			fileName, fileExtension = os.path.splitext(path)
			fileExtensionUpper = fileExtension.upper()
			if fileExtensionUpper != ".UX" and fileExtensionUpper != ".UNOSLN" and fileExtensionUpper != ".UNOPROJ":
				return False

		return True

def contains_unoproj(path):
	return os.path.isdir(path) and len([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)) and f.lower().endswith(".unoproj")])

class FusePreviewCurrent(sublime_plugin.TextCommand):
	def run(self, edit, type = "Local"):
		sublime.run_command("fuse_preview", {"type": type, "paths": [self.view.file_name()]});

	def is_enabled(self, type):
		return FusePreview.is_enabled(None, type, [self.view.file_name()])

	def is_visible(self, type):
		return FusePreview.is_visible(None, type, [self.view.file_name()])

class FuseToggleSelection(sublime_plugin.WindowCommand):
	def run(self):
		setSetting("fuse_selection_enabled", not getSetting("fuse_selection_enabled"))
		isSet = getSetting("fuse_selection_enabled")
		log().info("Selection enabled was set to %s", str(isSet))
		if isSet is False:
			gFuse.msgManager.sendEvent(gFuse.interop, "Fuse.Preview.SelectionChanged", 
			{
				"Path": "",
				"Text": "",
				"CaretPosition": {"Line": 1, "Character": 1}
			})


	def is_checked(self):
		return getSetting("fuse_selection_enabled")

def error_message(message):
	log().error(message.replace("\n", "\\n"))
	sublime.error_message(message)
