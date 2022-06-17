import tempfile
import os.path
import plistlib
import shutil
import zipfile
import re
import io
import sys

import pdb

try:
    from toolLog import Log
    from classCol import ColM
    from classRedescription import Redescription
    from classData import Data
    from classQuery import Query
    from classConstraints import Constraints, ActionsRegistry
    from classPreferencesManager import getPreferencesReader, EXT_SIREN, PATT_QALT
except ModuleNotFoundError:
    from .toolLog import Log
    from .classCol import ColM
    from .classRedescription import Redescription
    from .classData import Data
    from .classQuery import Query
    from .classConstraints import Constraints, ActionsRegistry
    from .classPreferencesManager import getPreferencesReader, EXT_SIREN, PATT_QALT


def make_filepath(filename,  basic_parts=None, default_suff="_alt", default_ext=""):
    # filename can be either
    # + -> filepath is built from the basic_parts if they are not None
    # a full path -> directly returned as filepath
    # a basename (no path, but an extension) -> combined to the path from basic_parts is it is not None
    # a suffix (no path, no extension) -> combined to basic_parts, instead of default_suff
    if filename is None or len(filename) == 0:
        return None
    ext = None
    if basic_parts is not None:
        ext = basic_parts[-1]
    if (default_ext is not None and len(default_ext) > 0):
        ext = default_ext

    if basic_parts is not None and filename == "+":  # filename is + -> make filename from basic
        return os.path.join(basic_parts[0], basic_parts[1] + default_suff + ext)
    elif len(filename) > 0 or (default_ext is not None and len(default_ext) > 0):
        head_n, tail_n = os.path.split(filename)
        if len(head_n) > 0:  # if folder is provided, use it
            return filename
        elif basic_parts is not None:  # otherwise use from basic if possible
            root_n, ext_n = os.path.splitext(tail_n)
            if len(ext_n) > 0:  # if extension -> complete basename
                return os.path.join(basic_parts[0], root_n + ext_n)
            return os.path.join(basic_parts[0], basic_parts[1] + filename + ext)


class Package(object):
    """Class to handle the zip packages that contain data, preferences, results, etc. for redescription mining.
    """

    # CONSTANTS
    # Names of the files in the package
    DATA_FILENAMES = ["data_LHS.csv",
                      "data_RHS.csv"]

    REDESCRIPTIONS_FILENAME = "redescriptions.csv"
    PREFERENCES_FILENAME = "preferences.xml"
    FDEFS_FILENAME = {"fields_vdefs": "fields_vdefs_custom.txt",
                      "fields_rdefs": "fields_rdefs_custom.txt",
                      "actions_rdefs": "actions_rdefs_custom.txt"}
    PLIST_FILE = "info.plist"
    PACKAGE_NAME = "siren_package"

    FILETYPE_VERSION = 6
    XML_FILETYPE_VERSION = 3

    RED_FN_SEP = ";"

    CREATOR = "Clired/Siren Package"
    DEFAULT_EXT = EXT_SIREN
    DEFAULT_TMP = "siren"

    def __init__(self, filename, callback_mess=None, mode="r"):
        if filename is not None:
            filename = os.path.abspath(filename)
            if mode != "w" and not os.path.isfile(filename):
                raise IOError("File does not exist")
            if mode != "w" and not zipfile.is_zipfile(filename):
                raise IOError("File is of wrong type")
        self.filename = filename
        self.callback_mess = callback_mess
        self.plist = dict(creator=self.CREATOR,
                          filetype_version=self.FILETYPE_VERSION)

    def __str__(self):
        return "PACKAGE: %s" % self.filename

    def raiseMess(self):
        if self.callback_mess is not None:
            self.callback_mess()

    def getFilename(self):
        return self.filename

    def getPackagename(self):
        return self.plist.get("package_name")

    def getFormatV(self):
        return self.plist.get("filetype_version", -1)

    def isOldXMLFormat(self):
        return self.getFormatV() <= self.XML_FILETYPE_VERSION

    def isLatestFormat(self):
        return self.getFormatV() == self.FILETYPE_VERSION

    def getSaveFilename(self):
        svfilename = self.filename
        if self.isOldXMLFormat():
            parts = self.filename.split(".")
            if len(parts) == 1:
                svfilename += "_new"
            elif len(parts) > 1:
                svfilename = ".".join(parts[:-1]) + "_new." + parts[-1]
        return svfilename

    def getNamelist(self):
        return self.package.namelist()

    def closePack(self):
        if self.package is not None:
            self.package.close()
            self.package = None

    def openPack(self):
        try:
            self.package = zipfile.ZipFile(self.filename, "r")
            # plist_fd = self.package.open(self.PLIST_FILE, "r")
            # self.plist = plistlib.readPlist(plist_fd)
            plist_ffd = self.package.read(self.PLIST_FILE)
            self.plist = plistlib.loads(plist_ffd)
        except Exception:
            self.package = None
            self.plist = {}
            self.raiseMess()
            raise

# READING ELEMENTS
##########################

    def read(self, preferences_reader, options_args=None, pv=None, params_only=False):
        elements_read = {}
        self.openPack()
        try:
            preferences = self.readPreferences(preferences_reader, options_args, pv)
            if preferences is not None:
                elements_read["preferences"] = preferences

            if not params_only:
                if "actions_rdefs" in self.plist:
                    ar_fns = []
                    for f in self.plist["actions_rdefs"].split(";"):
                        ff = f.strip()
                        if len(ff) > 0:
                            ar_fns.append(self.package.open(ff))
                    if len(ar_fns) > 0:
                        AR = ActionsRegistry(ar_fns)
                        if "preferences" in elements_read:
                            elements_read["preferences"]["AR"] = AR
                        else:
                            elements_read["preferences"] = {"AR": AR}
                    for fn in ar_fns:
                        fn.close()

                if "fields_vdefs" in self.plist:
                    fields_fns = []
                    for f in self.plist["fields_vdefs"].split(";"):
                        ff = f.strip()
                        if len(ff) > 0:
                            fields_fns.append(self.package.open(ff))
                    ColM.extendRP(fields_fns)
                    for fn in fields_fns:
                        fn.close()

                if "fields_rdefs" in self.plist:
                    fields_fns = []
                    for f in self.plist["fields_rdefs"].split(";"):
                        ff = f.strip()
                        if len(ff) > 0:
                            fields_fns.append(self.package.open(ff))
                    Redescription.extendRP(fields_fns)
                    for fn in fields_fns:
                        fn.close()

                add_info = IOTools.getDataAddInfo(preferences, plist=self.plist, version=self.getFormatV())
                data = self.readData(add_info)
                if data is not None:
                    if "ext_keys" in self.plist:
                        ext_keys = self.plist["ext_keys"].strip().split(";")
                        params_collect = data.loadExtensions(ext_keys=ext_keys, filenames=self.plist, params=preferences, details={"package": self.package})
                        preferences.update(params_collect)
                        data.recomputeCols()
                    elements_read["data"] = data
                    reds = self.readRedescriptions(data)
                    if reds is not None and len(reds) > 0:
                        elements_read["reds"] = reds
        finally:
            self.closePack()
        return elements_read

    def readPreferences(self, preferences_reader, options_args=None, pv=None):
        # Load preferences
        preferences = None
        if "preferences_filename" in self.plist:
            fd = None
            try:
                fd = self.package.open(self.plist["preferences_filename"], "r")
                preferences, _, _ = preferences_reader.getPreferences(options_args, conf_file=fd, pv=pv)
            except Exception:
                self.raiseMess()
                raise
            finally:
                if fd is not None:
                    fd.close()
        return preferences

    def readData(self, add_info):
        data = None
        if add_info is None:
            add_info = [{}, Data.NA_str]
        # Load data
        if "data_LHS_filename" in self.plist:
            try:
                fdLHS = io.TextIOWrapper(io.BytesIO(self.package.read(self.plist["data_LHS_filename"])))
                if self.plist.get("data_RHS_filename", self.plist["data_LHS_filename"]) != self.plist["data_LHS_filename"]:
                    fdRHS = io.TextIOWrapper(io.BytesIO(self.package.read(self.plist["data_RHS_filename"])))
                else:
                    fdRHS = None
                data = Data([fdLHS, fdRHS]+add_info, "csv")
            except Exception:
                data = None
                self.raiseMess()
                raise
            finally:
                fdLHS.close()
                if fdRHS is not None:
                    fdRHS.close()
        return data

    def readRedescriptions(self, data):
        reds = []
        # Load redescriptions
        rp = Redescription.getRP()
        if "redescriptions_filename" in self.plist:
            for file_red in self.plist["redescriptions_filename"].split(self.RED_FN_SEP):
                sid = ("%s" % (len(reds) + 1))[::-1]
                try:
                    fd = io.TextIOWrapper(io.BytesIO(self.package.read(file_red)))
                    # fd = self.package.open(file_red, "r")
                    rs, _ = rp.parseRedList(fd, data, sid=sid)
                except Exception:
                    self.raiseMess()
                    raise
                finally:
                    fd.close()
                reds.append({"items": rs, "src": ("file", file_red, 1)})
        return reds

# WRITING ELEMENTS
##########################
    def getTmpDir(self):
        return tempfile.mkdtemp(prefix=self.DEFAULT_TMP)

    # The saving function
    def writeToFile(self, filename, contents):
        # Store old package_filename
        old_package_filename = self.filename
        self.filename = os.path.abspath(filename)
        # Get a temp folder
        tmp_dir = self.getTmpDir()
        # package_dir = os.path.join(tmp_dir, filename)
        # os.mkdir(package_dir)

        # Write plist
        plist, filens = self.makePlistDict(contents)
        try:
            plistlib.writePlist(plist, os.path.join(tmp_dir, self.PLIST_FILE))
        except IOError:
            shutil.rmtree(tmp_dir)
            self.filename = old_package_filename
            self.raiseMess()
            raise

        # Write data files
        if "data" in contents:
            try:
                filenames = [os.path.join(tmp_dir, plist["data_LHS_filename"]), None]
                if plist.get("data_RHS_filename", plist["data_LHS_filename"]) != plist["data_LHS_filename"]:
                    filenames[1] = os.path.join(tmp_dir, plist["data_RHS_filename"])
                IOTools.writeData(contents["data"], filenames, toPackage=True)
                IOTools.writeDataExtensions(contents["data"], plist, tmp_dir)
            except IOError:
                shutil.rmtree(tmp_dir)
                self.filename = old_package_filename
                self.raiseMess()
                raise

        # Write redescriptions
        if "redescriptions" in contents:
            for rs in contents["redescriptions"]:
                try:
                    IOTools.writeRedescriptions(rs.get("items", []), os.path.join(tmp_dir, os.path.basename(rs["src"][1])),
                                                names=False, with_disabled=True, toPackage=True)
                except IOError:
                    shutil.rmtree(tmp_dir)
                    self.filename = old_package_filename
                    self.raiseMess()
                    raise

        # Write preferences
        if "preferences" in contents:
            try:
                IOTools.writePreferences(contents["preferences"], contents["preferences_reader"],
                                         os.path.join(tmp_dir, plist["preferences_filename"]), toPackage=True)
            except IOError:
                shutil.rmtree(tmp_dir)
                self.filename = old_package_filename
                self.raiseMess()
                raise

        for k in self.FDEFS_FILENAME.keys():
            if k in contents:
                fn = os.path.join(tmp_dir, plist[k])
                try:
                    with open(fn, "w") as f:
                        f.write(contents[k])
                except IOError:
                    shutil.rmtree(tmp_dir)
                    self.filename = old_package_filename
                    self.raiseMess()
                    raise

        # All"s there, so pack
        try:
            package = zipfile.ZipFile(self.filename, "w")
            package.write(os.path.join(tmp_dir, self.PLIST_FILE),
                          arcname=os.path.join(".", self.PLIST_FILE))
            for eln, element in filens.items():
                package.write(os.path.join(tmp_dir, element),
                              arcname=os.path.join(".", element),
                              compress_type=zipfile.ZIP_DEFLATED)
        except Exception:
            shutil.rmtree(tmp_dir)
            self.filename = old_package_filename
            self.raiseMess()
            raise
        finally:
            package.close()

        # All"s done, delete temp file
        shutil.rmtree(tmp_dir)

    def makePlistDict(self, contents):
        """Makes a dict to write to plist."""
        d = dict(creator=self.CREATOR,
                 filetype_version=self.FILETYPE_VERSION)

        if self.filename is None:
            d["package_name"] = self.PACKAGE_NAME
        else:
            (pn, suffix) = os.path.splitext(os.path.basename(self.filename))
            if len(pn) > 0:
                d["package_name"] = pn
            else:
                d["package_name"] = self.PACKAGE_NAME

        fns = {}
        if "data" in contents:
            d["NA_str"] = contents["data"].NA_str
            fns["data_LHS_filename"] = self.DATA_FILENAMES[0]
            if not contents["data"].isSingleD():
                fns["data_RHS_filename"] = self.DATA_FILENAMES[1]
            ext_keys = contents["data"].getActiveExtensionKeys()
            if len(ext_keys) > 0:
                d["ext_keys"] = ";".join(ext_keys)
            fns.update(contents["data"].getExtensionsActiveFilesDict())

        if "preferences" in contents:
            fns["preferences_filename"] = self.PREFERENCES_FILENAME
        for k, fn in self.FDEFS_FILENAME.items():
            if k in contents:
                fns[k] = fn
        d.update(fns)

        if "redescriptions" in contents and len(contents["redescriptions"]) > 0:
            base_names = [os.path.basename(c["src"][1]) for c in contents["redescriptions"]]
            d["redescriptions_filename"] = self.RED_FN_SEP.join(base_names)
            for ci, c in enumerate(base_names):
                fns["redescriptions_filename_%d" % ci] = c
        return d, fns


class IOTools:
    NA_FILETYPE_VERSION = 4
    map_data_params = [{"trg": 0, "from": "delim_in", "to": "delimiter",
                        "vmap": {"(auto)": None, "TAB": "\t", "SPC": " "}},
                       {"trg": 1, "from": "NA_str", "to": "NA_str"},
                       {"trg": 1, "from": "time_dayfirst", "to": "time_dayfirst",
                        "vmap": {"(auto)": None, "yes": True, "no": False}},
                       {"trg": 1, "from": "time_yearfirst", "to": "time_yearfirst",
                        "vmap": {"(auto)": None, "yes": True, "no": False}}]

    @classmethod
    def getDataAddInfo(tcl, params={}, plist={}, version=None, add_info=None):
        if add_info is None:
            add_info = [{}, {"NA_str": Data.NA_str_def}]

        for p in tcl.map_data_params:
            for src in [params, plist]:
                if p["from"] in src:
                    val = src[p["from"]]
                    if "vmap" in p:
                        val = p["vmap"].get(val, val)
                        if val is not None:
                            add_info[p["trg"]][p["to"]] = val
                    else:
                        add_info[p["trg"]][p["to"]] = val
        if add_info[1]["NA_str"] is None and (version is not None and version <= tcl.NA_FILETYPE_VERSION):
            add_info[1]["NA_str"] = Data.NA_str_def
        # print("ADD_INFO", add_info)
        return add_info

    @classmethod
    def writeRedescriptions(tcl, reds, filename, names=[None, None], with_disabled=False, toPackage=False, style="", full_supp=False, nblines=1, supp_names=None, modifiers={}, fmts=[None, None, None]):
        if names is False:
            names = [None, None]
        red_list = [red for red in reds if red.isEnabled() or with_disabled]
        if toPackage:
            fields_supp = [-1, ":extra:status"]
        else:
            fields_supp = None
        rp = Redescription.getRP()
        if filename != "+" and filename != "-":
            f = open(filename, mode="w")
        else:
            f = sys.stdout
        if style == "tex":
            f.write(rp.printTexRedList(red_list, names, fields_supp, nblines=nblines, modifiers=modifiers, fmts=fmts))
        else:
            f.write(rp.printRedList(red_list, names, fields_supp, full_supp=full_supp, supp_names=supp_names, nblines=nblines, modifiers=modifiers, fmts=fmts))
        if filename != "+" and filename != "-":
            f.close()

    @classmethod
    def writeRedescriptionsFmt(tcl, reds, filename, data):
        rp = Redescription.getRP()
        params = tcl.getPrintParams(filename, data)
        params["modifiers"] = rp.getModifiersForData(data)
        tcl.writeRedescriptions(reds, filename, **params)

    @classmethod
    def writePreferences(tcl, preferences, preferences_reader, filename, toPackage=False, inc_def=False, conf_filter=None):
        with open(filename, "w") as f:
            f.write(preferences_reader.dispParameters(preferences, defaults=inc_def, conf_filter=conf_filter))

    @classmethod
    def writeData(tcl, data, filenames, toPackage=False):
        data.writeCSV(filenames)

    @classmethod
    def writeDataExtensions(tcl, data, plist=None, tmp_dir="./"):
        if plist is not None:
            data.saveExtensions(plist, {"tmp_dir": tmp_dir})

    @classmethod
    def saveAsPackage(tcl, filename, data, preferences=None, preferences_reader=None, reds=None, AR=None):
        package = Package(None, None, mode="w")

        (filename, suffix) = os.path.splitext(filename)
        contents = {}
        if data is not None:
            contents["data"] = data
        if reds is not None and len(reds) > 0:
            contents["redescriptions"] = (self.REDESCRIPTIONS_FILENAME, reds, range(len(reds)))
        if preferences is not None:
            if preferences_reader is None:
                preferences_reader = getPreferencesReader()
            contents["preferences"] = preferences
            contents["preferences_reader"] = preferences_reader

        # definitions
        vdefs = ColM.getRP().fieldsToStr()
        if len(vdefs) > 0:
            contents["fields_vdefs"] = vdefs
        rdefs = Redescription.getRP().fieldsToStr()
        if len(rdefs) > 0:
            contents["fields_rdefs"] = rdefs
        if AR is not None:
            adefs = AR.actionsToStr()
            if len(adefs) > 0:
                contents["actions_rdefs"] = adefs

        package.writeToFile(filename+suffix, contents)

    @classmethod
    def getPrintParams(tcl, filename, data=None):
        # HERE
        basename = os.path.basename(filename)
        params = {"with_disabled": False, "style": "", "full_supp": False, "nblines": 1,
                  "names": [None, None], "supp_names": None}

        named = re.search("[^a-zA-Z0-9]named[^a-zA-Z0-9]", basename) is not None
        supp_names = (re.search("[^a-zA-Z0-9]suppnames[^a-zA-Z0-9]", basename) is not None) or \
                     (re.search("[^a-zA-Z0-9]suppids[^a-zA-Z0-9]", basename) is not None)

        params["with_disabled"] = re.search("[^a-zA-Z0-9]all[^a-zA-Z0-9]", basename) is not None
        params["full_supp"] = (re.search("[^a-zA-Z0-9]support[^a-zA-Z0-9]", basename) is not None) or supp_names

        if re.search(".tex$", basename):
            params["style"] = "tex"

        tmp = re.search("[^a-zA-Z0-9](?P<nbl>[1-3]).[a-z]*$", basename)
        if tmp is not None:
            params["nblines"] = int(tmp.group("nbl"))

        if named and data is not None:
            params["names"] = data.getNames()
            params["fmts"] = data.getFmts()
        if supp_names:
            params["supp_names"] = data.getRNames()
        return params

    @classmethod
    def prepareFilenames(tcl, params, tmp_dir=None, src_folder=None):
        filenames = {"style_data": "csv",
                     "add_info": tcl.getDataAddInfo(params)
                     }

        params_filenames = params.get("filename", {})

        for p in ["result_rep", "data_rep", "extensions_rep"]:
            if p not in params:
                params[p] = ""
            if sys.platform != "win32":
                if src_folder is not None and re.match("./", params[p]):
                    params[p] = src_folder+params[p][1:]
                elif params[p] == "__TMP_DIR__":
                    if tmp_dir is None:
                        tmp_dir = tempfile.mkdtemp(prefix="siren")
                    params[p] = tmp_dir + "/"
                elif sys.platform != "darwin":
                    params[p] = re.sub("~", os.path.expanduser("~"), params[p])

        # Make data file names
        filenames["LHS_data"] = ""
        if len(params_filenames.get("data_file", [])) > 0:
            filenames["LHS_data"] = params_filenames["data_file"][0]
        elif len(params.get("LHS_data", "")) != 0:
            filenames["LHS_data"] = params["LHS_data"]
        elif len(params.get("data_l", "")) != 0:
            filenames["LHS_data"] = params["data_rep"]+params["data_l"]+params.get("ext_l", "")

        filenames["RHS_data"] = ""
        if len(params_filenames.get("data_file", [])) > 0:
            if len(params_filenames.get("data_file")) == 1:
                filenames["RHS_data"] = params_filenames["data_file"][0]  # only one data file: use for both sides
            else:
                filenames["RHS_data"] = params_filenames["data_file"][1]  # more than one data file: first to RHS
                if len(params_filenames["data_file"]) > 2:
                    params_filenames["queries_file"] = params_filenames["data_file"][2:]+params_filenames.get("queries_file", [])  # the rest, queries
        elif len(params.get("RHS_data", "")) != 0:
            filenames["RHS_data"] = params["RHS_data"]
        elif len(params.get("data_r", "")) != 0:
            filenames["RHS_data"] = params["data_rep"]+params["data_r"]+params.get("ext_r", "")

        if len(params.get("trait_data", "")) != 0:
            filenames["traits_data"] = params["traits_data"]
        elif len(params.get("data_t", "")) != 0:
            filenames["traits_data"] = params["data_rep"]+params["data_t"]+params.get("ext_t", "")

        if os.path.splitext(filenames["LHS_data"])[1] != ".csv" or os.path.splitext(filenames["RHS_data"])[1] != ".csv":
            filenames["style_data"] = "multiple"
            filenames["add_info"] = []

        if len(params.get("extensions_names", "")) != 0:
            filenames["extensions"] = {}
            extkf = params.get("extensions_names", "")
            for blck in extkf.strip().split(";"):
                parts = [p.strip() for p in blck.split("=")]
                if len(parts) == 2:
                    filenames["extensions"]["extf_"+parts[0]] = params["extensions_rep"] + parts[1]

        # Make queries file names
        all_queries = []
        queries_basic = "-"
        if len(params.get("queries_file", "")) != 0:
            queries_basic = params["queries_file"]
            all_queries.append(queries_basic)
        elif params.get("out_base", "-") != "-" and len(params["out_base"]) > 0 and len(params.get("ext_queries", ".queries")) > 0:
            queries_basic = params["result_rep"]+params["out_base"]+params.get("ext_queries", ".queries")
            all_queries.append(queries_basic)

        # Make alternate query file name
        if len(params.get("queries_alternate", "")) > 0:
            tmp = re.match(PATT_QALT, params["queries_alternate"])
            if tmp is not None:
                alt_suff = tmp.group("suff")
                queries_alternate = tcl.makeUpName(queries_basic, alt_suff)
            else:
                queries_alternate = params["queries_alternate"]
            if not os.path.isfile(queries_alternate) and queries_alternate != "-":
                try:
                    tfs = open(queries_alternate, "a")
                    tfs.close()
                    os.remove(queries_alternate)
                except IOError:
                    print("Alternate queries file [%s] not writable..." % queries_alternate)
                    queries_alternate = "-"
                else:
                    all_queries.append(queries_alternate)

        for qfilename in params_filenames.get("queries_file", []):
            tmp = re.match(PATT_QALT, qfilename)
            if tmp is not None:
                alt_suff = tmp.group("suff")
                queries_alternate = tcl.makeUpName(queries_basic, alt_suff)
            else:
                queries_alternate = qfilename

            if queries_alternate != "-":
                if queries_basic == "-":
                    queries_basic = queries_alternate
                all_queries.append(queries_alternate)

        if not os.path.isfile(queries_basic) and queries_basic != "-":
            try:
                tfs = open(queries_basic, "a")
                tfs.close()
                os.remove(queries_basic)
            except IOError:
                print("Queries file [%s] not writable..." % queries_basic)
                queries_basic = "-"

        filenames["queries"] = queries_basic
        filenames["all_queries"] = all_queries

        if filenames["queries"] != "-":
            head_q, tail_q = os.path.split(filenames["queries"])
            root_q, ext_q = os.path.splitext(tail_q)
            basic_parts = (head_q, root_q, ext_q)
            filenames["basis"] = os.path.join(head_q, root_q)
        else:
            filenames["basis"] = ""

        build_files = [("queries_named", "queries_named_file", "_named", None),
                       ("support", "support_file", "_support", params.get("ext_support")),
                       ("logfile", "logfile", "", params.get("ext_log")),
                       ("pairs_store", "pairs_store", "_pairs", params.get("ext_log"))]
        # Make named queries file name
        for (path_param, file_param, default_suff, default_ext) in build_files:
            fpath = make_filepath(params.get(file_param),  basic_parts, default_suff, default_ext)
            if fpath is not None:
                filenames[path_param] = fpath

        if len(params.get("series_id", "")) > 0:
            for k in filenames.keys():
                if type(filenames[k]) is str:
                    filenames[k] = filenames[k].replace("__SID__", params["series_id"])

        if src_folder is not None and re.match("/", src_folder):
            ks = list(filenames.keys()) + list(filenames.get("extensions", {}).keys())
            for k in ["all_queries"]:
                for i in range(len(filenames[k])):
                    if len(filenames[k][i]) > 0 and filenames[k][i] != "-" and not re.match("/", filenames[k][i]):
                        filenames[k][i] = src_folder+"/"+filenames[k][i]

            for k in ks:
                if k not in ["style_data", "add_info", "extensions", "all_queries"] \
                        and len(filenames[k]) > 0 and filenames[k] != "-" and not re.match("/", filenames[k]):
                    filenames[k] = src_folder+"/"+filenames[k]

        return filenames

    @classmethod
    def outputResults(tcl, filenames, results, data=None, with_headers=True, mode="w", data_recompute=None):
        rp = Redescription.getRP()
        modifiers, modifiers_recompute = {}, {}
        if data is not None:
            modifiers = rp.getModifiersForData(data)
        if data_recompute is not None:
            modifiers_recompute = rp.getModifiersForData(data_recompute)
        fstyle = "basic"

        header_recompute = ""
        if data_recompute is not None:
            fields_recompute = rp.getListFields("stats", modifiers_recompute)
            header_recompute = rp.dispHeaderFields(fields_recompute) + "\tacc_diff"

        filesfp = {"queries": None, "queries_named": None, "support": None}
        if filenames["queries"] == "-":
            filesfp["queries"] = sys.stdout
        else:
            filesfp["queries"] = open(filenames["queries"], mode)
        all_fields = rp.getListFields(fstyle, modifiers)
        if with_headers:
            if len(header_recompute) > 0:
                filesfp["queries"].write(rp.dispHeaderFields(all_fields)+"\t"+header_recompute+"\n")
            else:
                filesfp["queries"].write(rp.dispHeaderFields(all_fields)+"\n")

        names = None
        if data is not None and data.hasNames() and "queries_named" in filenames:
            names = data.getNames()
            filesfp["queries_named"] = open(filenames["queries_named"], mode)
            if with_headers:
                filesfp["queries_named"].write(rp.dispHeaderFields(all_fields)+"\t"+header_recompute+"\n")

        if "support" in filenames:
            filesfp["support"] = open(filenames["support"], mode)

        # TO DEBUG: output all shown in siren, i.e. no filtering
        addto = ""
        for org in results:
            if data_recompute is not None:
                red = org.copy()
                red.recompute(data_recompute)
                acc_diff = (red.getAcc()-org.getAcc())/org.getAcc()
                addto = "\t"+red.disp(list_fields=fields_recompute)+"\t%f" % acc_diff
            filesfp["queries"].write(org.disp(list_fields=all_fields)+addto+"\n")
            if filesfp["queries_named"] is not None:
                filesfp["queries_named"].write(org.disp(names, list_fields=all_fields)+addto+"\n")
            if filesfp["support"] is not None:
                filesfp["support"].write(org.dispSupp()+"\n")

        for (ffi, ffp) in filesfp.items():
            if ffp is not None and filenames.get(ffi, "") != "-":
                ffp.close()

    @classmethod
    def loadAll(tcl, arguments=[], conf_defs=None, tasks=[], tasks_default=None, tasks_load={}, conf_filter=None):

        preferences_reader = getPreferencesReader(conf_defs, tasks, tasks_default)
        params, leftover_args, preferences_mod = preferences_reader.getPreferences(arguments)

        task_load = tasks_load.get(params["task"], {})
        params_only = task_load.get("params_only", False)
        if params["task"] in tasks_load:
            if conf_filter is None:
                conf_filter = task_load.get("conf_defs")
            else:
                conf_filter = conf_filter + task_load.get("conf_defs", [])
        else:
            conf_defs = None
        if params_only and len(preferences_mod) == 0:
            params["usage"] = True
        msg = preferences_reader.processHelp(params, conf_filter=conf_filter)
        if msg is not None:
            return False, msg

        package = None
        pack_filename = None
        config_filename = None
        tmp_dir = None
        reds = None
        leftover_args = None
        exec_folder = os.path.dirname(os.path.abspath(__file__))

        if "src_folder" in params.get("filename", {}):
            src_folder = params["filename"]["src_folder"]
        else:
            src_folder = exec_folder

        if "pack_file" in params.get("filename", {}):
            pack_filename = params["filename"]["pack_file"][0]
            package = Package(pack_filename)
            elements_read = package.read(preferences_reader, params_only=params_only, pv={})
            params_more = params
            params = elements_read.get("preferences", {})
            params.update(params_more)
            if not params_only:
                data = elements_read.get("data", None)
                reds = elements_read.get("reds", None)
                tmp_dir = package.getTmpDir()

        if params_only:
            return True, {"params": params, "leftover_args": leftover_args,
                          "preferences_reader": preferences_reader, "preferences_mod": preferences_mod}

        filenames = tcl.prepareFilenames(params, tmp_dir, src_folder)
        if task_load.get("with_log", True):
            logger = Log(verbosity=params["verbosity"], output=filenames["logfile"])
        else:
            logger = None

        if pack_filename is None:
            data = Data([filenames["LHS_data"], filenames["RHS_data"]]+filenames["add_info"], filenames["style_data"])
            data.loadExtensions(ext_keys=params.get("activated_extensions", []), filenames=filenames.get("extensions"), params=params)
            if (data is not None) and (reds is None) and ("queries" in filenames) and os.path.exists(filenames["queries"]):
                # attempt loading redescriptions from file
                try:
                    rp = Redescription.getRP()
                    with open(filenames["queries"]) as fd:
                        rs, _ = rp.parseRedList(fd, data, sid="1")  # avoid rid collisions
                except IOError:
                    # not able to load redescriptions from the file
                    rs = []
                reds = [{"items": rs, "src": ("file", filenames["queries"], 1)}]

        if logger is not None and task_load.get("log", True):
            logger.printL(2, data, "log")

        if pack_filename is not None:
            filenames["package"] = os.path.abspath(pack_filename)
        # print(filenames)
        return True, {"params": params, "leftover_args": leftover_args,
                      "preferences_reader": preferences_reader, "preferences_mod": preferences_mod,
                      "data": data, "reds": reds,
                      "logger": logger, "filenames": filenames, "package": package}

    @classmethod
    def getRedsEtc(tcl, loaded, alt_suff="_alt"):  # HERE -> USE
        all_queries_src = dict([(q, {"alt_pos": i, "pack_pos": None}) for (i, q) in enumerate(loaded["filenames"].get("all_queries", []))])
        reds = []
        srcs_reds = []
        unloaded = []
        if loaded["reds"] is not None:
            count_red_lists = len(loaded["reds"])
            for i in range(len(loaded["reds"])):
                src = loaded["reds"][i]["src"][1]
                if src in all_queries_src:
                    all_queries_src[src]["pack_pos"] = i
                else:
                    all_queries_src[src] = {"alt_pos": None, "pack_pos": i}
                all_queries_src[src]["nb_reds"] = len(loaded["reds"][i]["items"])
                all_queries_src[src]["pos"] = len(srcs_reds)
                reds.extend(loaded["reds"][i]["items"])
                srcs_reds.append(src)

        for src, poss in all_queries_src.items():
            if poss["pack_pos"] is None:
                redsi = None
                if os.path.exists(src):
                    # the file exists and redescriptions have not yet been loaded from it
                    rp = Redescription.getRP()
                    sid = ("%s" % (len(srcs_reds) + 1))[::-1]  # avoid rid collisions
                    try:
                        with open(src) as fd:
                            redsi, _ = rp.parseRedList(fd, loaded["data"], sid=sid)
                    except IOError:
                        redsi = None
                if redsi is not None:
                    all_queries_src[src]["nb_reds"] = len(redsi)
                    all_queries_src[src]["pos"] = len(srcs_reds)
                    reds.extend(redsi)
                    srcs_reds.append(src)
                else:
                    unloaded.append(src)

        # done loading reds, now decide what to use for output
        if len(unloaded) != 0:
            trg_reds = unloaded[-1]
        else:  # makeup name from queries filename and suffix
            trg_reds = tcl.makeUpName(loaded["filenames"].get("queries", "-"), alt_suff)
        return reds, srcs_reds, all_queries_src, trg_reds

    @classmethod
    def makeUpName(tcl, qfilename=None, alt_suff="_XXX"):
        if qfilename is None:
            trg = alt_suff
        elif qfilename == "-":
            trg = "-"
        else:
            parts = qfilename.split(".")
            if len(parts) > 1:
                if "." in alt_suff:
                    trg = ".".join(parts[:-2] + [parts[-2] + alt_suff])
                else:
                    trg = ".".join(parts[:-2] + [parts[-2] + alt_suff, parts[-1]])
            else:
                trg = qfilename + alt_suff
        return trg
