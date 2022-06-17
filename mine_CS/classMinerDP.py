
import re
import numpy

try:
    from toolLog import Log
    from classContent import BatchCollection
    from classRedescription import Redescription
    from classCandidates import initCands
    from classSouvenirs import Souvenirs
    from classConstraints import Constraints

    from classCharbonGMiss import CharbonGMiss
    from classCharbonGStd import CharbonGStd

    from classMiner import DummyLog, RCollection

except ModuleNotFoundError:
    from .toolLog import Log
    from .classContent import BatchCollection
    from .classRedescription import Redescription
    from .classCandidates import initCands
    from .classSouvenirs import Souvenirs
    from .classConstraints import Constraints

    from .classCharbonGMiss import CharbonGMiss
    from .classCharbonGStd import CharbonGStd

    from .classMiner import DummyLog, RCollection

import pdb


CHARBON_MISS_FORCE = False
# CHARBON_MISS_FORCE = True


def testIni(pair):
    if pair is None:
        return False
    return True


class MinerDP(object):

    # INITIALIZATION
    ##################
    def __init__(self, data, params, logger=None, mid=None, qin=None, cust_params={}, filenames={}):
        self.count = "-"
        self.qin = qin
        self.org_data = None
        self.up_souvenirs = True
        self.want_to_live = True
        if mid is not None:
            self.id = mid
        else:
            self.id = 1
        self.data = data

        self.max_processes = params["nb_processes"]
        self.pe_balance = params["pe_balance"]

        self.M = {}

        # SETTING UP DATA
        row_ids = None
        if "area" in cust_params:
            inw, outw = cust_params.get("in_weight", 1), cust_params.get("out_weight", 1)
            if "in_weight" in params:
                inw = params["in_weight"]
            if "out_weight" in params:
                outw = params["out_weight"]
            weights = dict([(r, outw) for r in range(self.data.nbRows())])
            for old in cust_params["area"]:
                weights[old] = inw
            cust_params["weights"] = weights

        keep_rows = None
        if self.data.hasSelectedRows() or self.data.hasLT():
            keep_rows = self.data.getVizRows({"rset_id": "learn"})
            if "weights" not in cust_params:
                row_ids = dict([(v, [k]) for (k, v) in enumerate(keep_rows)])

        if "weights" in cust_params:
            row_ids = {}
            off = 0
            for (old, mul) in cust_params["weights"].items():
                if keep_rows is None or old in keep_rows:
                    row_ids[old] = [off+r for r in range(mul)]
                    off += mul

        if row_ids is not None:
            self.org_data = self.data
            self.data = self.data.subset(row_ids)

        if logger is not None:
            self.logger = logger
        else:
            self.logger = Log()
        self.constraints = Constraints(params, self.data, filenames=filenames)

        self.age_threshold = self.constraints.getCstr("age")
        self.q_budget = self.constraints.getCstr("dp_budget_qual")*self.constraints.getCstr("dp_budget")
        self.max_query_length = self.constraints.getCstr("max_var_s0")
        self.min_acc = self.constraints.getCstr("min_acc")
        self.nb_ext_rounds = self.constraints.getCstr("nb_extension_rounds")

        self.charbon = self.initCharbon()
        self.rcollect = RCollection(self.data.usableIds(self.constraints.getCstr("min_itm_c"), self.constraints.getCstr("min_itm_c")),
                                    self.constraints.getCstr("amnesic"))
        self.logger.printL(1, "Miner set up (%s)" % self.charbon.getAlgoName(), "log", self.getLogId())
        self.logger.printL(1, "\t%s" % self.data.getInfo(), "log", self.getLogId())
        self.logger.printL(1, "\t%s" % self.rcollect, "log", self.getLogId())

        SEED_MAX = 2**30
        seeds_series = numpy.random.randint(SEED_MAX)
        numpy.random.seed(seeds_series)
        self.logger.printL(1, "Rnd seed (%d)" % seeds_series, "log", self.getLogId())

    def getId(self):
        return self.id

    def getLogId(self):
        return "%s" % self.getId()

    def shareRCollect(self):
        return self.rcollect.toShare()

    def shareLogger(self):
        return None
        # return self.logger
        # if not self.logger.usesOutMethods():
        #     return self.logger
        # return None

    def initCharbon(self):
        if True:  # INIT GREEDY CHARBON
            # if self.constraints.getCstr("add_condition"):
            #     if not self.data.isConditional() and self.data.isGeospatial():
            #         self.data.prepareGeoCond()

            if CHARBON_MISS_FORCE or self.data.hasMissing():
                return CharbonGMiss(self.constraints, logger=self.shareLogger())
            else:
                return CharbonGStd(self.constraints, logger=self.shareLogger())

    def kill(self):
        self.want_to_live = False

    def questionLive(self):
        if self.want_to_live and self.qin is not None:
            try:
                piece_result = self.qin.get_nowait()
                if piece_result["type_message"] == "progress" and piece_result["message"] == "stop":
                    self.want_to_live = False
            except:
                pass
        return self.want_to_live

# RUN FUNCTIONS
################################

    def full_run(self, cust_params={}):
        self.rcollect.resetFinal()
        self.count = 0
        self.logger.printL(1, "Start mining", "status", self.getLogId())

        # progress initialized after listing pairs
        self.logger.clockTic(self.getLogId(), "pairs")
        self.initializeRedescriptions()
        self.logger.clockTac(self.getLogId(), "pairs")
        self.logger.clockTic(self.getLogId(), "full run")

        self.doExpansions(cust_params)
        self.logger.clockTac(self.getLogId(), "full run", "%s" % self.questionLive())
        if not self.questionLive():
            self.logger.printL(1, "Interrupted!", "status", self.getLogId())
        else:
            self.logger.printL(1, "Done.", "status", self.getLogId())
        self.logger.sendCompleted(self.getLogId())
        self.rcollect.dispTracksEnd(self.logger, self.getLogId())
        return self.rcollect


####################################################
# INITIAL PAIRS
####################################################

    def initializeRedescriptions(self, ids=None):
        if True:
            done = None
            self.logger.printL(1, "Searching for initial pairs", "status", self.getLogId())
            explore_list = self.getInitExploreList(ids, done)
            #self.logger.initProgressFull(self.constraints, explore_list, self.rcollect.getNbAvailableCols(), 1, self.getLogId())

            self.charbon.setStore(self.data.nbRows(), self.constraints.getSSetts(), self.constraints, "P")
            total_pairs = len(explore_list)
            pairs = 0
            for prs, (idL, v) in enumerate(explore_list.items()):
                # self.charbon.store.toNextVar(idL)
                for (idR, pload) in v:
                    pairs += 1
                    #self.logger.updateProgress({"rcount": self.count, "pair": pairs, "pload": pload})
                    if pairs % 100 == 0:
                        self.logger.printL(3, "Searching pair %d/%d (%i <=> %i)" %
                                           (pairs, total_pairs, idL, idR), "status", self.getLogId())
                        #self.logger.updateProgress(level=3, id=self.getLogId())
                    elif pairs % 10 == 0:
                        self.logger.printL(7, "Searching pair %d/%d (%i <=> %i)" %
                                           (pairs, total_pairs, idL, idR), "status", self.getLogId())
                        #self.logger.updateProgress(level=7, id=self.getLogId())
                    else:
                        self.logger.printL(10, "Searching pair %d/%d (%i <=> %i)" %
                                           (pairs, total_pairs, idL, idR), "status", self.getLogId())

                    self.charbon.computePair(self.data.col(0, idL), self.data.col(1, idR), self.data.getColsC(), self.data)

            self.logger.printL(1, "Done searching initial pairs", "log", self.getLogId())
            for ci, cx in self.charbon.getStore().items():
                self.logger.printL(3, "%s-%f\t%s" % (ci[0], ci[1], cx), "log", self.getLogId())

            #self.logger.updateProgress(level=1, id=self.getLogId())
            # for pairs, (idL, idR, pload) in enumerate(explore_list):

            #     self.logger.updateProgress({"rcount": self.count, "pair": pairs, "pload": pload})
            #     if pairs % 100 == 0:
            #         self.logger.printL(3, "Searching pair %d/%d (%i <=> %i)" %
            #                            (pairs, total_pairs, idL, idR), "status", self.getLogId())
            #         self.logger.updateProgress(level=3, id=self.getLogId())
            #     elif pairs % 10 == 0:
            #         self.logger.printL(7, "Searching pair %d/%d (%i <=> %i)" %
            #                            (pairs, total_pairs, idL, idR), "status", self.getLogId())
            #         self.logger.updateProgress(level=7, id=self.getLogId())
            #     else:
            #         self.logger.printL(10, "Searching pair %d/%d (%i <=> %i)" %
            #                            (pairs, total_pairs, idL, idR), "status", self.getLogId())

            #     self.charbon.computePair(self.data.col(0, idL), self.data.col(1, idR), self.data.getColsC(), self.data)

            # self.logger.printL(1, "Done searching initial pairs", "log", self.getLogId())
            # self.logger.updateProgress(level=1, id=self.getLogId())

    def getInitExploreList(self, ids, done=set()):
        #explore_list = []
        explore_list = {}
        if ids is None:
            ids = self.data.usableIds(self.constraints.getCstr("min_itm_c"), self.constraints.getCstr("min_itm_c"))

        # ### WARNING DANGEROUS few pairs for DEBUG!
        # if self.data.nbCols(0) > 100:
        # ids = [[6], [9]]
        # ids = [[1], [9]]
        # ids = [[2], [29]]
        # ids = [[0], [75]]
        for idL in ids[0]:
            explore_list[idL] = []
            for idR in ids[1]:
                if not self.data.arePairTypesIn(idL, idR, tset=self.constraints.getCstr("inits_types_exclude")) and self.data.areGroupCompat(idL, idR) and \
                        (not self.data.isSingleD() or idR > idL or idR not in ids[0] or idL not in ids[1]):
                    if done is None or (idL, idR) not in done:
                        #explore_list.append((idL, idR, self.getPairLoad(idL, idR)))
                        explore_list[idL].append((idR, self.getPairLoad(idL, idR)))
                    else:
                        self.logger.printL(3, "Loaded pair (%i <=> %i)" % (idL, idR), "status", self.getLogId())
        return explore_list

    def getPairLoad(self, idL, idR):
        # pdb.set_trace()
        # print(idL, idR, eval("0b"+"".join(["%d" %(((idL+idR)%10)%i ==0) for i in [8,4,2]])))
        # + ((idL + idR)%10)/1000.0
        return max(1, self.data.col(0, idL).getNbValues() * self.data.col(1, idR).getNbValues()/50) + 1./(1+((idL + idR) % 10))
        # return max(1, self.data.col(0, idL).getNbValues()* self.data.col(1, idR).getNbValues()/50)
        # return PAIR_LOADS[self.data.col(0, idL).type_id-1][self.data.col(1, idR).type_id-1]

####################################################
# EXPANSIONS
####################################################
    def doExpansions(self, cust_params={}):
        nb_round = 0
        Q = self.charbon.getStore().getFoundReds(self.data)
        nextge = []
        rlist = []
        for red in Q:
            red.setPrivateSuppSizes((self.q_budget/(len(Q)*self.nb_ext_rounds*2)))
            if red.getAcc() >= self.min_acc:
                nextge.append(red)

        for i in range(self.nb_ext_rounds): 
            if nextge:
                self.count += 1

                self.logger.clockTic(self.getLogId(), "expansion_%d-%d" % (self.count, 0))

                nbexts = len(nextge)
                self.constraints.resetExtensionNB(nbexts)
                self.expandRedescriptions(nextge, self.rcollect)
                #self.logger.updateProgress({"rcount": self.count}, 1, self.getLogId())

                if self.logger.verbosity >= 4:
                    self.logger.printL(4, str(self.charbon.getStore()), "log", self.getLogId())
                    
                nextge = []
                for r0, r in list(self.M.items()):
                    r.setPrivateSuppSizes((self.q_budget/(nbexts*self.nb_ext_rounds*2)))
                    if r.getAcc() >= self.min_acc:
                        nextge.append(r)
                    else:
                        r0.setPrivateSuppSizes(-1)
                        rlist.append(r0)
                self.M = {}
  
        for r in nextge:
            rlist.append(r)
            
        for r in rlist:
            self.rcollect.addItem(r, "P")

        if self.rcollect.getLen("P") > 0:
            self.rcollect.selected(self.constraints.getActionsList("final"), ids="F", new_ids="P", trg_lid="F")

        self.logger.clockTac(self.getLogId(), "expansion_%d-%d" % (self.count, 0), "%s" % self.questionLive())
        self.logger.logResults(self.rcollect, "F", self.getLogId())

    def expandRedescriptions(self, nextge, rcollect=None):
        max_var = None  # [self.constraints.getCstr("max_var", side=0), self.constraints.getCstr("max_var", side=1)]

        for r in nextge:
            r.initAvailable(rcollect, self.data, max_var)

        for red in nextge:
            red.unsetPrivateSuppSizes()
            self.charbon.setStore(self.data.nbRows(), self.constraints.getSSetts(), self.constraints)
            if red.hasAvailableCols():
                #self.logger.printL(2, "Expansion %s.%s\t%s" % (self.count, redi, red), "log", self.getLogId())
                exts, basis_red, modr = red.prepareExtElems(self.data, self.data.isSingleD())  # ,max_len=self.max_query_length)
                self.charbon.getStore().setCurrent(red)
                self.charbon.getStore().add(None)

                # WARNING DANGEROUS few extensions for DEBUG!
                for (side, v, r) in exts:
                    if not self.questionLive():
                        nextge = []
                    else:
                        self.charbon.computeExpand(side, self.data.col(side, v), r, self.data.getColsC())

            if self.charbon.getStore():
                found_red = self.charbon.getStore().getFoundRedsKey(self.data)
                self.M[red] = list(found_red.values())[0]
             



#######################################################################
# MINER INSTANCIATION
#######################################################################

def instMinerDP(data, params, logger=None, mid=None, qin=None, cust_params={}, filenames={}):
    return MinerDP(data, params, logger, mid, qin, cust_params, filenames)
