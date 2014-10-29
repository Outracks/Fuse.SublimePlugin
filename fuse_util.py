import sublime
import os

def GetSetting(key,default=None):
	s = sublime.load_settings("Fuse.sublime-settings")
	return s.get(key, default)

def IsSupportedSyntax(syntaxName):	
	return syntaxName == "Uno" or syntaxName == "UX"

def GetExtension(path):
	base = os.path.basename(path)
	return os.path.splitext(base)[0]

def LoadFile(filePath):
	f = open(filePath, "r")
	return f.read()

def GetRowCol(view, pos):
	rowcol = view.rowcol(pos)
	rowcol = (rowcol[0] + 1, rowcol[1] + 1)
	return {"Line": rowcol[0], "Character": rowcol[1]}