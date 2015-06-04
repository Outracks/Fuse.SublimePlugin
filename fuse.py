import sublime, sublime_plugin, traceback
import json, threading, time, sys, os, time
from types import *
from Fuse.interop import *
from Fuse.cmd_parser import *
from Fuse.fuse_parseutils import *
from Fuse.fuse_util import *
from Fuse.go_to_definition import *
from Fuse.build_results import *
from Fuse.output_view import *
from Fuse.build_output import *

gFuse = None

class Fuse():
	apiVersion = (1,2)
	remoteApiVersion = None
	items = None
	isUpdatingCache = False
	autoCompleteEvent = None
	closeEvent = None
	interop = None
	buildResults = None
	outputView = OutputView()
	buildOutput = BuildOutputView()
	connectThread = None
	useShortCompletion = False
	wordAtCaret = ""

	def __init__(self):
		self.interop = Interop(self.Recv, self.SendHandshake)

	def Recv(self, msg):
		try:
			parsedRes = CmdParser.ParseCommand(msg)
			name = parsedRes[0]
			args = parsedRes[1]

			if name == "SetAPIVersion":
				self.HandleAPIVersion(args)
			if name == "SetCodeSuggestions":
				self.HandleCodeSuggestion(args)
			if name == "WriteToConsole":
				self.WriteToConsole(args)
			if name == "Error":
				self.Error(args)
			if name == "GoToDefinitionResponse":
				self.GoToDefinition(args)		
			if name == "BuildEventRaised":
				self.BuildEventRaised(args)
			if name == "NewBuild":				
				self.buildResults = BuildResults(sublime.active_window())
		except:
			print(sys.exc_info()[0])

	def HandleAPIVersion(self, args):
		versionString = args["Version"]
		tags = versionString.split(".")
		self.remoteApiVersion = (int(tags[0]), int(tags[1]))
		print(str.format("Remote Fuse plugin API version {0}.{1}", self.remoteApiVersion[0], self.remoteApiVersion[1]))
		print(str.format("Local Fuse plugin API version {0}.{1}", self.apiVersion[0], self.apiVersion[1]))
		if(self.remoteApiVersion[1] > 1):
			if self.apiVersion[0] > self.remoteApiVersion[0] or self.apiVersion[1] > self.remoteApiVersion[1]:
				sublime.error_message(
					str.format("This plugin expects Fuse plugin API {0}.{1}\nAvailable plugin API is {2}.{3}\nMake sure you are running the latest version of Fuse.", 
						self.apiVersion[0], self.apiVersion[1], 
						self.remoteApiVersion[0], self.remoteApiVersion[1]))

	def Error(self, cmd):
		print("Fuse - Error: " + cmd["ErrorString"])
		self.autoCompleteEvent.set()
		self.autoCompleteEvent.clear()

	def WriteToConsole(self, args):
		typeOfConsole = args["Type"]
		if typeOfConsole == "DebugLog":
			outputView.Write(args["Text"])
		elif typeOfConsole == "BuildLog":
			buildOutput.Write(args["Text"])

	def BuildEventRaised(self, cmd):
		buildResults.Add(cmd)

	def HandleCodeSuggestion(self, cmd):
		suggestions = cmd["CodeSuggestions"]

		self.isUpdatingCache = cmd["IsUpdatingCache"]
		self.items = []

		try:
			# Determine which fields are enabled for completions
			# If remoteApiVersion hasn't been defined, base fields on that
			# Version no used to pick fields is determined from lowest minor version of local and remote

			minor = self.apiVersion[1]
			if self.remoteApiVersion != None:
				minor = min(self.apiVersion[1], self.remoteApiVersion[1])

			suggestedUXNameSpaces = []

			for suggestion in suggestions:

				outText = suggestionText = suggestion["Suggestion"]
				suggestionType = suggestion["Type"]
				hintText = "" # The right-column hint text

				if minor >= 1:
					if completionSyntax == "UX" and doCompleteAttribs and suggestionType == "Property":
						s = ParseUXSuggestion(wordAtCaret, suggestion, suggestedUXNameSpaces, useShortCompletion, foldUXNameSpaces)
						if(s == None):
							continue
						else:
							outText = s[0]
							suggestionText = s[0]+s[1]
						
					else:
						hintText = suggestion["ReturnType"]

						if suggestionType == "Method" or suggestionType == "Constructor":
							# Build sublime tab completion, type hint and verbose type hint
							parsedMethod = ParseMethod(suggestion["AccessModifiers"], suggestionText, suggestion["MethodArguments"], hintText, suggestionType == "Constructor")

							if not useShortCompletion:
								suggestionText = parsedMethod[0]
							hintText = parsedMethod[1]

						if suggestionType == "Field" or suggestionType == "Property":
							hintText = TrimType(hintText)


				if suggestion["PreText"] != "":
					suggestionText = suggestion["PreText"] + suggestion["PostText"]


				outText += "\t" + hintText
				if(wordAtCaret == "." or outText.casefold().find(wordAtCaret.casefold()) > -1):
					self.items.append((outText, suggestionText))

		except:
			traceback.print_exc()

		self.autoCompleteEvent.set()
		self.autoCompleteEvent.clear()

	def SendHandshake(self):
		self.interop.Send(json.dumps({"Command":"SetFeatures", "Arguments":
			{"Features":[{"Name":"CodeCompletion"}, 
			{"Name": "Console"}, 
			{"Name": "BuildEvent"},
			{"Name": "ShortcutFeature"}]}}))

def plugin_loaded():
	global gFuse
	gFuse = Fuse()
	gFuse.closeEvent = threading.Event()	
	gFuse.buildResults = BuildResults(sublime.active_window())

	gFuse.connectThread = threading.Thread(target = TryConnect)
	gFuse.connectThread.daemon = True
	gFuse.connectThread.start()

	s = sublime.load_settings("Preferences.sublime-settings")
	if GetSetting("fuse_open_files_in_same_window"):
		s.set("open_files_in_new_window", False)
	else:
		s.set("open_files_in_new_window", True)

def plugin_unloaded():
	global gFuse
	gFuse.closeEvent.set()
	gFuse.connectThread.join(1)
	gFuse = None

def TryConnect():	
	try:		
		while not gFuse.closeEvent.is_set():
			if GetSetting("fuse_enabled") == True and not gFuse.interop.IsConnected():
				gFuse.interop.Connect()			

			time.sleep(1)
	finally:
		gFuse.interop.Disconnect()

class FuseEventListener(sublime_plugin.EventListener):

	def on_modified(self, view):
		global useShortCompletion
		global wordAtCaret
		caret = view.sel()[0].a
		vstr = view.substr(caret)
		wordAtCaret = view.substr(view.word(caret)).strip()

		if vstr == "(" or vstr == "=": 
			useShortCompletion = True
		else:
			useShortCompletion = False

	def RequestAutoComplete(self, view, syntaxName):

		fileName = view.file_name()
		text = view.substr(sublime.Region(0,view.size()))
		caret = view.sel()[0].a

		gFuse.interop.Send(json.dumps({"Command":"RequestCodeCompletion", "Arguments":{
			"QueryId": 0,
			"Path": fileName, "Text": text, 
			"Type": syntaxName, "CaretPosition": GetRowCol(view, caret)}}))

	def on_query_completions(self, view, prefix, locations):
		global items
		global completionSyntax
		global doCompleteAttribs
		global foldUXNameSpaces

		if GetSetting("fuse_completion") == False or not gFuse.interop.IsConnected():
			return

		syntaxName = GetExtension(view.settings().get("syntax"))
		if not IsSupportedSyntax(syntaxName):
			return

		doCompleteAttribs = GetSetting("fuse_ux_attrib_completion")
		foldUXNameSpaces = GetSetting("fuse_ux_attrib_folding")

		completionSyntax = syntaxName

		self.RequestAutoComplete(view, syntaxName)

		autoCompleteEvent.wait(0.2)
		
		data = (items, sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS)
		if len(items) == 0:
			if self.isUpdatingCache == True:
				return ([("Updating suggestion cache...", "_"), ("", "")], sublime.INHIBIT_WORD_COMPLETIONS)

			if GetSetting("fuse_if_no_completion_use_sublime") == False:				
				return ([("", "")], sublime.INHIBIT_WORD_COMPLETIONS)
			else:
				return

		items = []
		return data

class DisconnectCommand(sublime_plugin.ApplicationCommand):
	def run(self):
		gFuse.interop.Disconnect()	

class ToggleBuildresCommand(sublime_plugin.ApplicationCommand):
	def run(self):	
		buildResults.ToggleShow()

class ToggleOutputviewCommand(sublime_plugin.ApplicationCommand):
	def run(self):
		outputView.ToggleShow()

class ToggleBuildoutputCommand(sublime_plugin.ApplicationCommand):
	def run(self):
		buildOutput.ToggleShow()

class GotoDefinitionCommand(sublime_plugin.TextCommand):
	def run(self, edit):		
		view = self.view

		syntaxName = GetExtension(view.settings().get("syntax"))		
		if not IsSupportedSyntax(syntaxName) or len(view.sel()) == 0:
			return

		text = view.substr(sublime.Region(0,view.size()))
		caret = view.sel()[0].a

		gFuse.interop.Send(json.dumps({"Command": "GotoDefinition", "Arguments":{
			"Path": view.file_name(),
			"Text": text,
			"Type": syntaxName,
			"CaretPosition": GetRowCol(view, caret),
			"QueryId": 0}}))

class FuseBuildRunCommand(sublime_plugin.ApplicationCommand):
	def run(self):
		gFuse.interop.Send(json.dumps({"Command": "BuildAndRun"}))

class FuseRecompileCommand(sublime_plugin.ApplicationCommand):
	def run(self):
		gFuse.interop.Send(json.dumps({"Command": "Recompile"}))
