# Copyright (C) 2007,2010-2013	Valek Filippov (frob@df.ru)
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of version 3 or later of the GNU General Public
# License as published by the Free Software Foundation.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301
# USA
#

import sys,struct,math
from utils import *
from midi import *

# returns size of the RIFF-based tree starting from 'parent'
def get_parent_size (page, parent):
	size = 8 # fourcc + chunk size
	for i in range(page.model.iter_n_children(parent)):
		citer = page.model.iter_nth_child(parent, i)
		size += len(page.model.get_value(citer,3)) + 8 # data size plus child fourcc and chunk size dwords
	return size

# collects tree under 'parent' inserting fourcc-s and chunk sizes
def collect_tree (page, parent):
	ctdata = ""
	if page.model.iter_n_children(parent) > 0:
		for i in range(page.model.iter_n_children(parent)):
			citer = page.model.iter_nth_child(parent, i)
			cdata = page.model.get_value(citer,3)
			clen = len(cdata)
			name = page.model.get_value(citer,1)[1]
			if name[:5] == "IPIT/":
				name = name[5:]
				pos = cdata.find("\x00")
				if pos != -1:
					clen = pos - 1
			ctdata += name + struct.pack(">I",clen)+cdata
		return page.model.get_value(parent,1)[1]+struct.pack(">I",len(ctdata))+ctdata
	else:
		ctdata = page.model.get_value(parent,3)
		name = page.model.get_value(parent,1)[1]
		clen = len(ctdata)
		if name == "SSTY":
			pos = ctdata.rfind("\x00\xFF\x2F\x00")
			if pos != -1:
				clen = pos + 4
		return name+struct.pack(">I",clen)+ctdata


# collects tree in VPRM, skips "vdblock" and "prtshdr"
def collect_vprm (page, parent):
	data = ""
	for i in range(page.model.iter_n_children(parent)):
		citer = page.model.iter_nth_child(parent, i)
		itype = page.model.get_value(citer,1)[1]
		if itype != "vdblock" and itype != "prtshdr":
			data += page.model.get_value(citer,3)
		if page.model.iter_n_children(citer) > 0:
			data += collect_vprm (page, citer)
	return data

# saves YEP file
def save (page, fname):
	data = ""
	iter1 = page.model.get_iter_first()
	while None != iter1:
		if page.model.get_value(iter1,1)[1] != "VPRM":
			data += collect_tree (page, iter1)
		else:
			tdata = collect_vprm (page, iter1)
			data += page.model.get_value(iter1,1)[1] + struct.pack(">I",len(tdata))+tdata
		iter1 = page.model.iter_next(iter1)
	f = open(fname,"wb")
	f.write(data)
	f.close()


def hdra(hd,data):
	off = 0
	var0 = struct.unpack(">I",data[off:off+4])[0]
	add_iter(hd,"Var0",var0,off,4,">I")
	off += 4
	size = struct.unpack(">I",data[off:off+4])[0]
	add_iter(hd,"Size",size,off,4,">I")
	off += 4
	ind = 0
	while off < size:
		item = struct.unpack(">h",data[off:off+2])[0]
		add_iter(hd,"Item %02x"%ind,"%02x"%item,off,2,">h")
		off += 2
		ind += 1

vprmfunc = {"hdra":hdra}

def hdr1item (page,data,parent,offset=0):
	off = 0
	# size of the "main header for level2 block
	# i.e. 'offset to the "parts header"'
	h1off0 = struct.unpack(">I",data[off:off+4])[0]
	if h1off0 != 0x24:
		print "ATTENTION! YEP: size of VPRM header2 is not 0x24, it's %02x"%h1off0
	off += 4
	vdtxt = "Drumkit"
	if ord(data[0x21]) == 0x3f:
		vdtxt = "Voice"
	vdidx = ord(data[0x23])
	h1citer = add_pgiter(page,"%s Block %d"%(vdtxt,vdidx),"vprm","vdblock",data,parent,"%02x  "%offset)
	add_pgiter(page,"V/Dk Header","vprm","vbhdr",data[:h1off0],h1citer,"%02x  "%offset)
	# offset to the list of offsets of parts
	h1off1 = struct.unpack(">I",data[off:off+4])[0]
	off += 4
	# this offset is used in Drumkits only
	h1off2 = struct.unpack(">I",data[off:off+4])[0]
	off += 4
	# seems to be 0s allways in files we have
	h1off3 = struct.unpack(">I",data[off:off+4])[0]
	off += 4
	# offset to the graph
	h1off4 = struct.unpack(">I",data[off:off+4])[0]
	off += 4

	# parse 'parts header'
	p1iter = add_pgiter(page,"Parts Header","vprm","prtshdr",data[h1off0:h1off1],h1citer,"%02x  "%(offset+h1off0))
	# first dozen in 'Parts header'
	add_pgiter(page,"Common settings","vprm","p1s0",data[h1off0:h1off0+12],p1iter,"%02x  "%(offset+h1off0))
	off = h1off0+12
	# number of parts for voice/drumkit
	p1num = struct.unpack(">I",data[off:off+4])[0]
	add_pgiter(page,"Num of sequences","vprm","p1num",data[off:off+4],p1iter,"%02x  "%(offset+off))
	off += 4
	# FIXME! Guessing that number of dozens would match with number of parts
	for i in range(p1num):
		add_pgiter(page,"PH seq%d"%(i+1),"vprm","p1s%d"%(i+1),data[off:off+12],p1iter,"%02x  "%(offset+off))
		off += 12
		if off > h1off1:
			print "ATTENTION! YEP: not enough bytes for 'dozens'..."
	
	# parse list of offsets to parts
	poffs = []
	# FIXME!  No validation that we do not cross the 1st offset to parts
	for i in range(p1num):
		poffs.append(struct.unpack(">I",data[h1off1+i*4:h1off1+i*4+4])[0])
	p2iter = add_pgiter(page,"Parts offsets","vprm","poffs",data[h1off1:h1off1+p1num*4],h1citer,"%02x  "%(offset+h1off1))

	# parse parts
	ind = 0
	try:
		for i in poffs:
			off = i
			# number of elements
			elnum = ord(data[off+4])
			piter = add_pgiter(page,"Part %d"%ind,"vprm","parthdr",data[off:off+176],h1citer,"%02x  "%(offset+off))
			off += 176
			ind += 1
			# collect elements
			# FIXME! we do not check for data bonds in the loop here
			for j in range(elnum):
				add_pgiter(page,"Element %d"%j,"vprm","elem",data[off:off+180],piter,"%02x  "%(offset+off))
				off += 180
	except:
		print "Failed in parsing parts","%02x"%i

	# add drumkit's "h1off2" block
	# FIXME!  Bold assumption that "h1off3 is 'reserved'
	if vdtxt == "Drumkit":
		diter = add_pgiter(page,"Drumkit block","vprm","dkblock",data[h1off2:h1off4],h1citer,"%02x  "%(offset+h1off2))

	# add graph
	diter = add_pgiter(page,"Graph","vprm","graph",data[h1off4:],h1citer,"%02x  "%(offset+h1off4))
	
def vprm (page, data, parent, offset=0):
	sig = data[:16]
	add_pgiter(page,"Signature","vprm","sign",data[:16],parent,"%02x  "%offset)
	off = 16
	ptr = struct.unpack(">I",data[off:off+4])[0]
	add_pgiter(page,"Offset to samples","vprm","offsmpl",data[off:off+4],parent,"%02x  "%(offset+off))
	off += 4

	hdr1end = struct.unpack(">I",data[off:off+4])[0]
	h1iter = add_pgiter(page,"Voices","vprm","voices",data[20:hdr1end],parent,"%02x  "%(offset+off))
	off += 4
	hdr1 = []
	while off < hdr1end:
		v = struct.unpack(">I",data[off:off+4])[0]
		if v != 0:
			hdr1.append(v)
		off += 4
	for i in hdr1:
		hdr1item (page,data[off:i],h1iter,(offset+off))
		off = i
	hdr1item (page,data[off:ptr],h1iter,(offset+off))

	off = ptr
	off2 = ptr
	v1 = struct.unpack(">I",data[off:off+4])[0] # ??? "allways" 8
	hdraend = struct.unpack(">I",data[off2+4:off2+8])[0]
	haiter = add_pgiter(page,"Header A","vprm","hdra",data[off:off+hdraend],parent,"%02x  "%(offset+off))
	off2 += hdraend
	hdrbend = off+struct.unpack(">I",data[off2:off2+4])[0]
	hbiter = add_pgiter(page,"Samples","vprm","samples",data[off+hdraend:hdrbend],parent,"%02x  "%(offset+off+hdraend))
	hdrb = []
	off2 += 4
	while off2 < hdrbend:
		v = struct.unpack(">I",data[off2:off2+4])[0]
		if v != 0:
			hdrb.append(v+off)
		off2 += 4
	ind = 0
	for i in hdrb:
		v1 = struct.unpack(">h",data[off2:off2+2])[0]
		v2 = struct.unpack(">h",data[off2+2:off2+4])[0]
		v3 = ord(data[off2+16])
		add_pgiter(page,"Block %04x (%04x %04x %02x [%s])"%(ind,v1,v2,v3,pitches[v3]),"vprm","hdrbch",data[off2:i],hbiter,"%02x  "%(offset+off2))
		off2 = i
		ind += 1
	v1 = struct.unpack(">h",data[off2:off2+2])[0]
	v2 = struct.unpack(">h",data[off2+2:off2+4])[0]
	v3 = ord(data[off2+16])
	add_pgiter(page,"Block %04x (%04x %04x %02x [%s])"%(ind,v1,v2,v3,pitches[v3]),"vprm","hdrbch",data[off2:],hbiter,"%02x  "%(offset+off2))


def parse (page, data, parent,align=4.,prefix=""):
	off = 0
	while off < len(data):
		fourcc = data[off:off+4]
		off += 4
		l = struct.unpack(">I",data[off:off+4])[0]
		if align:
			length = int(math.ceil(l/align)*align)
		else:
			length = l
		off += 4
		if fourcc == "SSTY":
			iname = fourcc+" %s"%(data[off:off+16])
		elif fourcc == "VVST":
			n = struct.unpack(">H",data[off+0x19:off+0x1b])[0]
			if ord(data[off+0x18]) == 0x3f:
				f = "[Voice %s]"%n
			else:
				f = "[DrumKit %s]"%n
			iname = fourcc+f+" %s"%(data[off:off+16])
		else:
			iname = "%s"%fourcc
		
		citer = add_pgiter(page,iname,"yep","%s%s"%(prefix,fourcc),data[off:off+length],parent)
		if fourcc == "VPRM":
			vprm (page, data[off:off+length], citer)
		if fourcc == "IPIT":
			parse (page, data[off:off+length], citer, 4., "IPIT/")
			
		off += length
	page.view.get_column(1).set_title("Offset")
	return "YEP"
