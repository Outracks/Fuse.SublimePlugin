import sublime
import os

def getSetting(key,default=None):
	s = sublime.load_settings("Fuse.sublime-settings")
	return s.get(key, default)

def getFusePathFromSettings():
	path = getSetting("fuse_path_override")
	if path == "" or path == None:
		return "fuse"
	else:
		return path+"/fuse"

def setSetting(key,value):
	s = sublime.load_settings("Fuse.sublime-settings")
	s.set(key, value)
	sublime.save_settings("Fuse.sublime-settings")

def isSupportedSyntax(syntaxName):	
	return syntaxName == "Uno" or syntaxName == "UX"

def getSyntax(view):
	try:
		return view.settings().get("syntax").split("/")[-1].split(".")[0]
	except:
		return ""

def getExtension(path):
	if path is None:
		return ""
		
	base = os.path.basename(path)
	ext = os.path.splitext(base)

	if ext is None:
		return ""
	else:
		return ext[1].strip(".")

def getRowCol(view, pos):
	rowcol = view.rowcol(pos)
	rowcol = (rowcol[0] + 1, rowcol[1] + 1)
	return {"Line": rowcol[0], "Character": rowcol[1]}
