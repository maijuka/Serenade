import re
import os.path
import numpy

try:
    from classSParts import cmp_lower, cmp_greater, cmp_leq, cmp_geq
    from classPreferencesManager import PreferencesReader
    from csv_reader import getFp, FOLDS_PATT

except ModuleNotFoundError:
    from .classSParts import cmp_lower, cmp_greater, cmp_leq, cmp_geq
    from .classPreferencesManager import PreferencesReader
    from .csv_reader import getFp, FOLDS_PATT

import pdb


class Constraints(object):

    @classmethod
    def applyVarsMask(tcl, data, params):
        if data is not None:
            return data.applyDisableMasks(params.get("mask_vars_LHS"), params.get("mask_vars_RHS"), params.get("mask_rows"))

    special_cstrs = {}

    params_sets = {"data": set(["parts_type", "method_pval"])}

    def __init__(self, params, data=None, AR=None, filenames={}):
        self.deps = []
        self.folds = None
        if AR is None:
            AR = params.get("AR")
        self._pv = PreferencesReader.copyParams(params)

        self._pv.update(self.prepareValues(params))
        if filenames is not None:
            self._pv.update(filenames)
        self.resetAR(AR)
        self.resetDataDependent(data, params)


    def calc_sensitivity(self,n, cutoff, scale):
        if cutoff < 1: cutoff = cutoff*n
        vals = numpy.zeros((n+1, n+1))
        q = lambda a, b: a / (b * (1 + numpy.exp(-scale * (a - cutoff))))
        for union_size in range(1, n+1):
            intersection_sizes = numpy.arange(1,union_size+1)
            vals[union_size, 1:union_size+1] = q(intersection_sizes, union_size)
        # First option: union gets one bigger, intersection stays unchanged
        # New value is smaller and one row below
        change_in_intersection = vals - numpy.roll(vals, -1, axis=0)
        change_in_intersection[-1,:] = 0 # Last row is just the original last row and meaningless
        # Second option: both change
        # New value is diagonally down and larger
        change_in_both = numpy.roll(vals, (-1, -1), axis=(0, 1)) - vals
        # Last row and column are still meaningless, but they are negative and can be ignored
        maximum_change = max(change_in_intersection.max(), change_in_both.max())
        print(f"Maximum change is {maximum_change}, where change in intersection is {change_in_intersection.max()} at location {numpy.unravel_index(numpy.argmax(change_in_intersection), (n+1, n+1))}")
        print(f"and change in both is {change_in_both.max()} at location {numpy.unravel_index(numpy.argmax(change_in_both), (n+1, n+1))}")
        return maximum_change

    ## SSETTS_PARAMS = set(["parts_type", "method_pval"])
    def reset(self, params, data=None, AR=-1, dtv=None):
        changed = {}
        self._pv.update(params)
        self._pv.update(self.prepareValues(params))

        if not isinstance(AR, ActionsRegistry):
            AR = params.get("AR", -1)
        changedAR = self.resetAR(AR)
        if changedAR:
            changed["actions_filters"] = True
        if data is not None and (dtv is None or len(self.params_sets["data"].intersection(dtv)) > 0):
            self.resetDataDetails(data)
            changed["reset_all"] = True
        self._pv.update(self.prepareValuesDataDependent(params))
        return changed

    def prepareValues(self, params, vals=None):
        def getNegBool(p):
            return p == "negative"

        def getOpsBool(p):
            return p == "disjunction"

        # preparing query types
        if vals is None:
            vvs = {}
        else:
            vvs = vals
        for side_id in [0, 1]:
            for type_id in [1, 2, 3]:
                kp = "neg_query_s%d_%d" % (side_id, type_id)
                if vals is None or kp in params:
                    vvs[kp] = [getNegBool(v) for v in params.get(kp, [])]

            kp = "ops_query_s%d" % side_id
            if vals is None or kp in params:
                vvs[kp] = [getOpsBool(v) for v in params.get(kp, [])]

        # preparing score coeffs
        if vals is None:
            vvs["score_coeffs"] = {}
        for k in ["impacc", "rel_impacc", "pval_red", "pval_query", "pval_fact"]:
            if vals is None or k in params:
                vvs["score_coeffs"][k] = params.get("score.%s" % k, 0)
        return vvs

    
    def prepareValuesDataDependent(self, params):
        # scaling support thresholds
        min_itm_c, min_itm_in, min_itm_out = self.scaleSuppParams(params.get("min_itm_c"), params.get("min_itm_in"), params.get("min_itm_out"))
        _, min_fin_in, min_fin_out = self.scaleSuppParams(-1, params.get("min_fin_in"), params.get("min_fin_out"))
        
        dp_sensitivity = self.calc_sensitivity(self.N, params.get("x0_ratio")*self.N, params.get("log_k"))
        
        return {"min_itm_c": min_itm_c, "min_itm_in": min_itm_in, "min_itm_out": min_itm_out,
                "min_fin_in": min_fin_in, "min_fin_out": min_fin_out,
                "dp_sensitivity": dp_sensitivity}


    def resetDataDetails(self, data):
        if data is not None:
            self.N = data.nbRows()
            data.resetSSetts(self.getCstr("parts_type"), self.getCstr("method_pval"))
            self.ssetts = data.getSSetts()
            self._pv["parts_type"] = self.ssetts.getTypeParts()
        else:
            self.N = -1
            self.ssetts = None
            
    def resetExtensionNB(self, extensions):
        self._pv["nb_extensions"] = extensions

    def resetDataDependent(self, data, params):
        self.applyVarsMask(data, params)
        if data is not None:
            data.setCompat(self.getCstr("var_compat"))
        self.resetDataDetails(data)
        self._pv.update(self.prepareValuesDataDependent(params))

    def resetAR(self, AR=None):
        ar_fns = []
        for f in self._pv.get("actions_rdefs", "").split(";"):
            ff = f.strip()
            if len(ff) > 0:
                ar_fns.append(ff)

        if AR is None:
            self.AR = ActionsRegistry()
            changed = True
        elif isinstance(AR, ActionsRegistry):
            self.AR = AR
            ar_fns = []
            changed = True
        else:
            changed = False

        if len(ar_fns) > 0:
            self.AR.extend(ar_fns)
            changed = True
        return changed

    def setFolds(self, data):
        fcol = data.getColsByName(FOLDS_PATT)
        if len(fcol) == 1:
            self.folds = data.getFoldsStats(fcol[0][0], fcol[0][1])

    def scaleF(self, f):
        if f == -1 or f is None:
            return -1
        if f >= 1:
            return int(f)
        elif f >= 0 and f < 1 and self.N != 0:
            return int(round(f*self.N))
        return 0

    def scaleSuppParams(self, min_c, min_in=None, min_out=None):
        sc_min_c = self.scaleF(min_c)
        if min_in == -1:
            sc_min_in = sc_min_c
        else:
            sc_min_in = self.scaleF(min_in)
        if min_out == -1:
            sc_min_out = sc_min_in
        else:
            sc_min_out = self.scaleF(min_out)
        return (sc_min_c, sc_min_in, sc_min_out)

    def getSSetts(self):
        return self.ssetts

    def getCstr(self, k, **kargs):
        if k in self.special_cstrs:
            return eval("self.%s" % self.special_cstrs[k])(**kargs)

        k_bak = k
        if "side" in kargs:
            k += "_s%d" % kargs["side"]
        if "type_id" in kargs:
            k += "_%d" % kargs["type_id"]

        if k in self._pv:
            return self._pv[k]
        else:
            return self._pv.get(k_bak, kargs.get("default"))

    # STATUS TEST TO KNOW WHAT IS ALLOWED
    @classmethod
    def expandDefStatus(tcl):
        return {"init": False, "other_contains_OR": False, "contains_OR": False, "other_type_id": 0, "type_id": 0, "cond": False}

    @classmethod
    def getExpandedStatus(tcl, status=0):
        if type(status) is dict:
            return status
        xpd = tcl.expandDefStatus()
        if cmp_lower(status, 0):
            xpd["init"] = True
        return xpd

    @classmethod
    def isStatusInitStage(tcl, status):
        if type(status) is dict:
            return status.get("init", False)
        return cmp_lower(status, 0)

    @classmethod
    def isStatusCond(tcl, status):
        if type(status) is dict:
            return status.get("cond", False)
        return False

    @classmethod
    def getStatusPair(tcl, col, side, fixTerm):
        status = tcl.expandDefStatus()
        status["init"] = True
        status["type_id"] = col.typeId()
        status["other_type_id"] = fixTerm.typeId()
        return status

    @classmethod
    def getStatusCond(tcl, pair=False):
        status = tcl.expandDefStatus()
        if pair:
            status["init"] = True
        status["cond"] = True
        return status

    @classmethod
    def getStatusRed(tcl, red=None, side=None, force_ops=None):
        if red is not None and side is not None:
            status = tcl.expandDefStatus()
            status["init"] = (red.length(side) == 0)
            status["force_ops"] = force_ops
            status["contains_OR"] = red.usesOr(side)
            status["other_contains_OR"] = red.usesOr(1-side)
            if red.length(1-side) == 1:
                status["other_type_id"] = red.query(1-side).invTerms().pop().typeId()
            if red.length(side) == 1:
                status["type_id"] = red.query(side).invTerms().pop().typeId()
            return status
        return 0

    # special constraints (not just lookup)
    def allw_ops(self, side, currentRStatus=0):
        if self.isStatusCond(currentRStatus):
            return [False]
        if self.isStatusInitStage(currentRStatus):
            return [True]
        else:
            xpd = self.getExpandedStatus(currentRStatus)
            if xpd.get("force_ops") is not None:
                return xpd.get("force_ops")
            tmp = self.getCstr("ops_query", side=side)
            if xpd["other_contains_OR"] and self._pv["single_side_or"]:
                tmp = [o for o in tmp if not o]
            return tmp
    special_cstrs["allw_ops"] = "allw_ops"

    def allw_negs(self, side, type_id, currentRStatus=0):
        if self.isStatusCond(currentRStatus):
            return [False]
        else:
            return self.getCstr("neg_query", side=side, type_id=type_id)
    special_cstrs["allw_negs"] = "allw_negs"

    def neg_query_init(self, side, currentRStatus=0):
        if self.isStatusInitStage(currentRStatus):
            xpd = self.getExpandedStatus(currentRStatus)
            if xpd["other_type_id"] > 0:
                return True in self.getCstr("neg_query", side=(1-side), type_id=xpd["other_type_id"])
        return False
    special_cstrs["neg_query_init"] = "neg_query_init"

    def getActionsList(self, k, action_substitute=None):
        return self.AR.getActionsListToGo(k, self, action_substitute)

    def getActionsRegistry(self):
        return self.AR

 # FOLDS
    # def filter_folds(self, red):
    #    if self.folds is None:
    #        return False

    #    bcountI = numpy.bincount(self.folds["folds"][list(red.getSuppI())], minlength=self.folds["nb_folds"])
    #    bcountU = numpy.bincount(self.folds["folds"][list(red.getSuppU())], minlength=self.folds["nb_folds"])
    #    bcountU[bcountU == 0] = 1
    #    accs = bcountI/(1.*bcountU)
    #    print "--------------------"
    #    print red.disp()
    #    print accs
    #    if len(numpy.where(accs >= red.getAcc())[0]) > 1:
    #        return False
    #        bb = accs # bcount/self.folds["counts_folds"]
    #        # bpr = bcount/float(numpy.sum(bcount))
    #        # entropS = -numpy.sum(numpy.log(bpr)*bpr)
    #        bpr = bb/numpy.max(bb)
    #        score = numpy.sum(bpr)
    #        print score
    #        # entropM = -numpy.sum(numpy.log(bpr)*bpr)
    #        if score > 1.5:
    #            return False
    #    return True

    # Dependencies between variables (ex, single dataset)

    def setDeps(self, deps=[]):
        self.deps = deps

    def getDeps(self, col=None):
        if col is None:
            return self.deps
        else:
            return self.deps[col]

    def hasDeps(self):
        return len(self.deps) > 0


############################################################
############################################################
def flipValue(v):
    nv = v
    if type(v) is bool:
        v = not nv
    elif nv is not None:
        try:
            v = -nv
        except TypeError:
            try:
                v = reversed(nv)
            except TypeError:
                v = nv
    return v


def doComparison(vA, cop, vB):
    if cop == "<":
        return cmp_lower(vA, vB)
    if cop == ">":
        return cmp_greater(vA, vB)
    if cop == "=":
        return vA == vB
    if cop == "<>":
        return vA != vB
    if cop == ">=":
        return cmp_geq(vA, vB)
    if cop == "<=":
        return cmp_leq(vA, vB)
    return False


class ActionsRegistry:

    pref_dir = os.path.dirname(os.path.abspath(__file__))
    def_file_basic = pref_dir+"/actions_rdefs_basic.txt"
    default_def_files = [def_file_basic]

    def __init__(self, actions_fns=[], strict=False):
        if not strict:
            actions_fns = self.default_def_files + actions_fns
        self.actions_lists = {}
        self.actions_compact = {}
        self.parsed_fns = []
        self.setupFDefsFiles(actions_fns)

    def actionsToStr(self):
        xps = ""
        for k, v in self.actions_compact.items():
            if v is not None:
                xps += "actionlist\t%s\n" % k
                for ff in v:
                    xps += "%s\n" % ff
        if len(xps) > 0:
            head = "# Action definitions read from %s\n" % ";".join(self.parsed_fns)
            xps = head + xps
        return xps

    def setupFDefsFiles(self, actions_fns):
        for actions_fn in actions_fns:
            default = actions_fn in self.default_def_files
            try:
                fp, fcl = getFp(actions_fn)
                self.readActionsFile(fp, default)
                if fcl:
                    fp.close()
                    if not default:
                        self.parsed_fns.append(actions_fn)
                else:
                    self.parsed_fns.append("package")
            except IOError:
                print("Cannot read actions defs from file %s!" % actions_fn)

    def extend(self, actions_fns=[]):
        self.setupFDefsFiles(actions_fns)

    def setActionsList(self, fk, flist, fcompact=None, default=False):
        self.actions_lists[fk] = flist
        if not default:
            self.actions_compact[fk] = fcompact
        else:
            self.actions_compact[fk] = None

    def delActionsList(self, fk):
        if fk in self.actions_lists:
            del self.actions_lists[fk]

    def getActionsKeys(self, public_only=True):
        if public_only:
            return [k for k in self.actions_lists.keys() if not re.match("_", k)]
        return list(self.actions_lists.keys())

    def getActionsKeysSimple(self, public_only=True, patt=None):
        ks = []
        for k in self.getActionsKeys(public_only):
            l = self.getActionsListRecurse(k)
            if len(l) == 1 and (patt is None or re.match(patt, l[0]["action"])):
                ks.append(k)
        return ks

    def getActionsKeysMulti(self, public_only=True, patt=None):
        ks = []
        for k in self.getActionsKeys(public_only):
            l = self.getActionsListRecurse(k)
            if len(l) > 1 and (patt is None or re.match(patt, l[0]["action"])):
                ks.append(k)
        return ks

    def clearActions(self):
        self.actions_lists = {}

    def hasActionsList(self, fk):
        return fk in self.actions_lists

    def getActionsList(self, fk):
        priv = "_"+fk
        if fk not in self.actions_lists and priv in self.actions_lists:
            return self.actions_lists[priv]
        return self.actions_lists.get(fk, [])

    def getActionsListRecurse(self, fk):
        actions = []
        for action in self.getActionsList(fk):
            if "actions" in action:
                actions.extend(self.getActionsListRecurse(action["actions"]))
            else:
                actions.append(action)
        return actions

    def getActionsListToGo(self, fk, constraints, action_substitute=None):
        actions = []
        for action in self.getActionsList(fk):
            if "actions" in action:
                actions.extend(self.getActionsListToGo(action["actions"], constraints))
            else:
                actions.append(self.fillActionConstraints(action, constraints))
        if action_substitute is not None:
            if action_substitute[1] is None:
                actions = [a for a in actions if a["action"] != action_substitute[0]]
            else:
                for i in range(len(actions)):
                    if actions[i]["action"] == action_substitute[0]:
                        actions[i]["action"] = action_substitute[1]
        return actions

    def fillBlockConstraints(self, block, constraints):
        if block[0]["typic"] == "CSTR":
            v = constraints.getCstr(block[0]["exp"])
            if block[0].get("flip"):
                v = flipValue(v)
            bA = {"typic": None, "exp": v}
        else:
            bA = {"typic": block[0]["typic"], "exp": block[0]["exp"]}
            if block[0].get("flip"):
                bA["flip"] = True
        if len(block) > 2:
            if block[2]["typic"] == "CSTR":
                v = constraints.getCstr(block[2]["exp"])
                if block[2].get("flip"):
                    v = flipValue(v)
                bB = {"typic": None, "exp": v}
            else:
                bB = {"typic": block[2]["typic"], "exp": block[2]["exp"]}
                if block[2].get("flip"):
                    bB["flip"] = True
            bb = (bA, block[1], bB)
        else:
            bb = (bA,)
        return bb

    def fillActionConstraints(self, action, constraints=None):
        filled = {}
        for k, v in action.items():
            if k == "action":
                filled[k] = v
            elif k == "blocks":
                filled[k] = [self.fillBlockConstraints(block, constraints) for block in v]
            else:
                if v[0] == "CSTR":
                    val = constraints.getCstr(v[1])
                    if val is None:
                        val = self.getArgDefault(k, action["action"])
                    else:
                        val = self.getArgType(k, action["action"])(val)
                    filled[k] = ("V", val)
                else:
                    filled[k] = v
        return filled

    def getArgDefault(self, arg, action):
        if action in self.basic_actions and arg in self.basic_actions[action]["args"]:
            return self.basic_actions[action]["args"][arg]

    def getArgType(self, arg, action):
        v = self.getArgDefault(arg, action)
        if v is not None:
            return type(v)

    # PRINT
    def disp(self, fks=None):
        if fks is None:
            fks = self.getActionsKeys()
        k_str = {}

        while len(fks) > 0:
            fk = fks.pop(0)
            strs = []
            for action in self.getActionsList(fk):
                if "actions" in action:
                    strs.append("list\t%s" % action["actions"])
                    if action["actions"] not in k_str and action["actions"] not in fks:
                        fks.append(action["actions"])
                else:
                    strs.append(self.action2str(action))
            k_str[fk] = strs
        xps = ""
        for fk, lines in k_str.items():
            if len(lines) > 0:
                xps += "\n".join(["actionlist\t%s" % fk]+lines)+"\n"
        return xps

    @classmethod
    def block2str(tcl, block):
        m = "-" if block[0].get("flip") else ""
        t = "%s:%s%s" % (block[0].get("typic"), m, block[0].get("exp"))
        if len(block) > 2:
            m = "-" if block[2].get("flip") else ""
            t += "%s%s:%s%s" % (block[1], block[2].get("typic"), m, block[2].get("exp"))
        return t

    @classmethod
    def action2str(tcl, action):
        t = ["%s" % action["action"]]
        b = []
        for k, v in action.items():
            if k == "blocks":
                b = [tcl.block2str(block) for block in v]
            elif k != "action":
                if v[0] == "CSTR":
                    t.append("%s=%s:%s" % (k, v[0], v[1]))
                else:
                    t.append("%s=%s" % (k, v[1]))
        return "\t".join(t+b)

    @classmethod
    def dispAction(tcl, action):
        t = []
        b = []
        for k, v in action.items():
            if k == "blocks":
                b = [tcl.block2str(block) for block in v]
            elif k != "action":
                if v[0] == "CSTR":
                    t.append("%s=%s:%s" % (k, v[0], v[1]))
                else:
                    t.append("%s=%s" % (k, v[1]))
        return "%s\t%s%s\n" % (action["action"], " ".join(t), "\n\t".join([""]+b))

    ##############################
    ##############################
    def getItemVal(exp, item, other=None, constraints=None, details={}, swap=False):
        if other is not None and swap:
            v = other.getExpProp(exp, details)
            return v, "[%s:%s:]%s" % (other.getShortId(), exp, v)
        if item is not None:
            v = item.getExpProp(exp, details)
            return v, "[%s:%s:]%s" % (item.getShortId(), exp, v)

    def getPairVal(exp, item, other=None, constraints=None, details={}, swap=False):
        if other is None:
            raise Exception("Pair comparison missing other item")
        if item is not None and other is not None:
            if swap:
                (item, other) = (other, item)
            v = item.getExpPairProp(other, exp, details)
            return v, "[%s:%s:%s]%s" % (item.getShortId(), exp, other.getShortId(), v)

    def getCstrVal(exp, item, other=None, constraints=None, details={}, swap=False):
        if constraints is None:
            raise Exception("No constraints can't evaluate %s" % exp)
        v = constraints.getCstr(exp)
        return v, "[%s]%s" % (exp, v)

    types_static = {"str": str, "int": int, "float": float, "tuple": tuple, "bool": bool}
    types_dynamic = {"ITEM": getItemVal, "PAIR": getPairVal, "CSTR": getCstrVal}
    ##############################
    ##############################

    # PARSING
    basic_actions = {"apply": {"parity": 1, "args": {"function": "identity", "reverse": False}},
                     "applyBulk": {"parity": 1, "args": {"function": "identity"}},
                     "sort": {"parity": 1, "args": {"reverse": False}},
                     "cut": {"parity": 2, "args": {"max": 0, "direction": 0, "reverse": False}},
                     "filterSingle": {"parity": 1, "args": {"reverse": False}},
                     "filterToFirst": {"parity": 2, "args": {"reverse": False}},
                     "filterLast": {"parity": 2, "args": {"reverse": False}},
                     "filterPairs": {"parity": 2, "args": {"max": 0, "reverse": False}}}
    cops = "<>="
    typic_patt = "(" + "|".join(list(types_static.keys())+list(types_dynamic.keys()))+")"
    block_patt = "(?P<block>(?P<typicA>"+typic_patt+"):(?P<modA>-?)(?P<expA>[^-"+cops+"][^"+cops+"]*)((?P<cop>"+"".join([c+"?" for c in cops])+")(?P<typicB>"+typic_patt+"):(?P<modB>-?)(?P<expB>[^-"+cops+"][^"+cops+"]*))?)$"
    @classmethod
    def parseComparisonBlock(tcl, block):
        mtch = re.match(tcl.block_patt, block)
        if mtch is not None:
            bA = {"typic": mtch.group("typicA"), "exp": mtch.group("expA")}
            if mtch.group("modA") is not None and len(mtch.group("modA")) > 0:
                if bA["typic"] in tcl.types_static:
                    bA["exp"] = mtch.group("modA")+bA["exp"]
                else:
                    bA["flip"] = True
            if mtch.group("cop") is not None and len(mtch.group("cop")) > 0:
                bB = {"typic": mtch.group("typicB"), "exp": mtch.group("expB")}
                if mtch.group("modB") is not None and len(mtch.group("modB")) > 0:
                    if bB["typic"] in tcl.types_static:
                        bB["exp"] = mtch.group("modB")+bB["exp"]
                    else:
                        bB["flip"] = True
                bb = (bA, mtch.group("cop"), bB)
            else:
                bb = (bA,)
            return bb

    def readActionsFile(self, actions_fp, default=False):
        current_list_actions = []
        current_list_compact = []
        current_list_name = None
        for line in actions_fp:
            ll = re.sub("\s*#.*$", "", line).strip()
            if len(ll) == 0:
                continue
            prts = ll.split("\t")
            if prts[0] in self.basic_actions and current_list_name is not None:
                action_dets = self.parseActionParts(prts)
                current_list_actions.append(action_dets)
                current_list_compact.append(line.strip())
            elif prts[0] == "list" and len(prts) == 2:
                current_list_actions.append({"actions": prts[1]})
                current_list_compact.append(line.strip())
            elif prts[0] == "actionlist" and len(prts) == 2:
                if current_list_name is not None and len(current_list_actions) > 0:
                    self.setActionsList(current_list_name, current_list_actions, current_list_compact, default)
                current_list_name = prts[1]
                current_list_actions = []
                current_list_compact = []
        if current_list_name is not None and len(current_list_actions) > 0:
            self.setActionsList(current_list_name, current_list_actions, current_list_compact, default)

    def parseActionParts(self, prts):
        if prts[0] in self.basic_actions:
            action_dets = {"action": prts[0]}
            if self.basic_actions[prts[0]].get("parity", 0) > 0:
                action_dets["blocks"] = []
            def_args = dict([(k, ("V", v)) for k, v in self.basic_actions[prts[0]].get("args", {}).items()])
            action_dets.update(def_args)
            args_patt = "(?P<arg>("+"|".join(list(def_args.keys()))+"))=(?P<cstr>CSTR:)?(?P<val>.*)$"
            for prt in prts[1:]:
                mtch_arg = re.match(args_patt, prt)
                if mtch_arg is not None:
                    arg = mtch_arg.group("arg")
                    if mtch_arg.group("cstr") is not None:
                        action_dets[arg] = ("CSTR", mtch_arg.group("val"))
                    else:
                        val = self.getArgType(arg, prts[0])(mtch_arg.group("val"))
                        action_dets[arg] = ("V", val)
                else:
                    block = self.parseComparisonBlock(prt)
                    if block is not None and "blocks" in action_dets:
                        if self.getParityBlock(block) == 1 and len(block) == 1 and self.basic_actions[prts[0]].get("parity", 0) == 2:
                            ####
                            block = (block[0], "=", block[0])
                        if self.getParityBlock(block) <= self.basic_actions[prts[0]].get("parity", 0):
                            action_dets["blocks"].append(block)
                        else:
                            raise Exception("Parity does not match! (%s vs. %s)" % (self.getParityBlock(block), self.basic_actions[prts[0]].get("parity", 0)))
            return action_dets

    # ACCESS
    @classmethod
    def trackValElem(tcl, block, item, other=None, constraints=None, swap=False):
        if block["typic"] in tcl.types_dynamic:
            v, t = tcl.types_dynamic[block["typic"]](block["exp"], item, other, constraints, swap=swap)
            if block.get("flip"):
                v = flipValue(v)
                t = "NOT "+t
            return v, t
        elif block["typic"] in tcl.types_static:
            v = tcl.types_static[block["typic"]](block["exp"])
            return v, "%s" % v
        elif block["typic"] is None:
            return block["exp"], "%s" % block["exp"]
        return None, "??"

    @classmethod
    def getValElem(tcl, block, item, other=None, constraints=None, swap=False):
        return tcl.trackValElem(block, item, other, constraints, swap)[0]

    @classmethod
    def evalBlock(tcl, block, item, other=None, constraints=None):
        (bA, cop, bB) = (tcl.getBlockElem("A", block), tcl.getBlockElem("cop", block), tcl.getBlockElem("B", block))
        vA = tcl.getValElem(bA, item, other, constraints, swap=False)
        if bB is not None:
            vB = tcl.getValElem(bB, item, other, constraints, swap=True)
            return doComparison(vA, cop, vB)
        return vA

    @classmethod
    def trackBlock(tcl, block, item, other=None, constraints=None):
        (bA, cop, bB) = (tcl.getBlockElem("A", block), tcl.getBlockElem("cop", block), tcl.getBlockElem("B", block))
        vA, tA = tcl.trackValElem(bA, item, other, constraints, swap=False)
        if bB is not None:
            vB, tB = tcl.trackValElem(bB, item, other, constraints, swap=True)
            v = doComparison(vA, cop, vB)
            return v, "%s%s?%s -> %s" % (tA, cop, tB, v)
        return vA, tA

    @classmethod
    def getBlocks(tcl, action):
        return action.get("blocks", [])

    @classmethod
    def getNbBlocks(tcl, action):
        return len(action.get("blocks", []))

    @classmethod
    def getArg(tcl, arg, action, constraints=None):
        if arg in action:
            if action[arg][0] == "CSTR":
                if constraints is None:
                    raise Exception("No constraints can't evaluate %s" % exp)
                return constraints.getCstr(action[arg][1])
            return action[arg][1]
        return None

    @classmethod
    def getParityBlock(tcl, block):
        if tcl.getBlockElem("typicA", block) == "PAIR" or tcl.getBlockElem("typicB", block) == "PAIR" or \
                (tcl.getBlockElem("typicA", block) == "ITEM" and tcl.getBlockElem("typicB", block) == "ITEM"):
            return 2
        return 1*(tcl.getBlockElem("typicA", block) == "ITEM" or tcl.getBlockElem("typicB", block) == "ITEM")

    @classmethod
    def getBlockElem(tcl, k, block):
        bb, kk = (None, "")
        if k == "cop":
            if len(block) > 1:
                return block[1]
        elif k[-1] == "B":
            if len(block) > 2:
                bb, kk = (block[2], k[:-1])
        elif k[-1] == "A":
            bb, kk = (block[0], k[:-1])
        else:
            bb, kk = (block, k)
        if bb is None or kk == "":
            return bb
        else:
            return bb.get(kk)


# c = Constraints(params={})
# AR = ActionsRegistry()
# for k in AR.getActionsKeys():
#     print "ACTION LIST", k
#     for action in AR.getActionsListToGo(k, c):
#         print AR.dispAction(action)
# # # print AR.actions2str()
