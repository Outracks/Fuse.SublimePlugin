import sublime
import os

def getSetting(key,default=None):
	s = sublime.load_settings("Fuse.sublime-settings")
	return s.get(key, default)

def getFusePathFromSettings():
	path = getSetting("fuse_path_override")
	if path == "" or path == None:
		if os.path.isfile("/usr/bin/fuse"):
			return "/usr/bin/fuse"
		else:
			return "/usr/local/bin/fuse"
	else:
		return path+"/fuse"

def setSetting(key,value):
	s = sublime.load_settings("Fuse.sublime-settings")
	s.set(key, value)
	sublime.save_settings("Fuse.sublime-settings")

def isSupportedSyntax(syntaxName):	
	return syntaxName == "Uno" or syntaxName == "UX"

def getExtension(path):
	base = os.path.basename(path)
	return os.path.splitext(base)[0]

def getRowCol(view, pos):
	rowcol = view.rowcol(pos)
	rowcol = (rowcol[0] + 1, rowcol[1] + 1)
	return {"Line": rowcol[0], "Character": rowcol[1]}
