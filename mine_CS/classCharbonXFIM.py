import numpy
try:

    from classData import Data
    from classCharbon import CharbonXaust
    from classQuery import *
    from classRedescription import Redescription
except ModuleNotFoundError:
    from .classData import Data
    from .classCharbon import CharbonXaust
    from .classQuery import *
    from .classRedescription import Redescription

import pdb

# -----------------------------------------------------------------------
# File    : pyfim.py
# Contents: frequent item set mining in Python
#           (in the current version only with the eclat algorithm)
# Author  : Christian Borgelt
# History : 2013.01.23 file created
#           2013.01.24 closed and maximal item set filtering improved
#           2013.01.25 recursion/output data combined in a list
#           2013.02.09 made compatible with Python 3 (print, range)
#           2017.06.02 bugs in perfect extension processing fixed
# -----------------------------------------------------------------------


def report(iset, pexs, supp, setts, store_handle):
    '''Recursively report item sets with the same support.
iset    base item set to report (list of items)
pexs    perfect extensions of the base item set (list of items)
supp    (absolute) support of the item set to report
setts    static recursion/output setts as a list
        [ target, supp, zmin, zmax, maxx, count [, out] ]'''
    if not pexs:                # if no perfect extensions (left)
        n = len(iset)           # check the item set size
        if (n < setts[2]) or (n > setts[3]):
            return
        store_handle((tuple(iset), supp))
    else:                       # if perfect extensions to process
        report(iset+[pexs[0]], pexs[1:], supp, setts, store_handle)
        report(iset,           pexs[1:], supp, setts, store_handle)

# -----------------------------------------------------------------------


def closed(tracts, elim):
    '''Check for a closed item set.
tracts  list of transactions containing the item set
elim    list of lists of transactions for eliminated items
returns whether the item set is closed'''
    for t in reversed(elim):    # try to find a perfect extension
        if tracts <= t:
            return False
    return True                 # return whether the item set is closed

# -----------------------------------------------------------------------


def maximal(tracts, elim, supp):
    '''Check for a maximal item set.
tracts  list of transactions containing the item set
elim    list of lists of transactions for eliminated items
supp    minimum support of an item set
returns whether the item set is maximal'''
    for t in reversed(elim):    # try to find a frequent extension
        if sum([w for x, w in tracts & t]) >= supp:
            return False
    return True                 # return whether the item set is maximal

# -----------------------------------------------------------------------


def recurse(tadb, iset, pexs, elim, setts, store_handle):
    '''Recursive part of the eclat algorithm.
tadb    (conditional) transaction settsbase, in vertical representation,
        as a list of item/transaction information, one per (last) item
        (triples of support, item and transaction set)
iset    item set (prefix of conditional transaction settsbase)
pexs    set of perfect extensions (parent equivalent items)
elim    set of eliminated items (for closed/maximal check)
setts    static recursion/output setts as a list
        [ target, supp, zmin, zmax, maxx, count [, out] ]'''
    tadb.sort()                 # sort items by (conditional) support
    xelm = []
    m = 0            # init. elim. items and max. support
    for k in range(len(tadb)):  # traverse the items/item sets
        s, i, t = tadb[k]         # unpack the item information
        if s > m:
            m = s         # find maximum extension support
        if setts[0] in 'cm' and not closed(t, elim+xelm):
            continue            # check for a perfect extension
        proj = []
        xpxs = []    # construct the projection of the
        for r, j, u in tadb[k+1:]:  # trans. settsbase to the current item:
            u = u & t           # intersect with subsequent lists
            r = sum([w for x, w in u])
            if r >= s:
                xpxs.append(j)
            elif r >= setts[1]:
                proj.append([r, j, u])
        xpxs = pexs + xpxs       # combine perfect extensions and
        xset = iset + [i]        # add the current item to the set and
        n = len(xpxs) if setts[0] in 'cm' else 0
        r = recurse(proj, xset, xpxs, elim+xelm, setts, store_handle) \
            if proj and (len(xset)+n < setts[4]) else 0
        xelm += [t]             # collect the eliminated items
        if setts[0] == 'm':    # if to report only maximal item sets
            if r < setts[1] and maximal(t, elim+xelm[:-1], setts[1]):
                report(xset+xpxs, [], s, setts, store_handle)
        elif setts[0] == 'c':    # if to report only closed  item sets
            if r < s:
                report(xset+xpxs, [], s, setts, store_handle)
        else:                   # if to report all frequent item sets
            report(xset, xpxs, s, setts, store_handle)
    return m                    # return the maximum extension support

# -----------------------------------------------------------------------


def mod_eclat(tracts, setts, store_handle):
    # prepare transaction data
    tadb = dict()               # reduce by combining equal transactions
    for t in [frozenset(t) for t in tracts]:
        if t in tadb:
            tadb[t] += 1
        else:
            tadb[t] = 1
    tracts = tadb.items()       # get reduced trans. and collect items
    items = set().union(*[t for t, w in tracts])
    tadb = dict([(i, []) for i in items])
    for t in tracts:            # collect transactions per item
        for i in t[0]:
            tadb[i].append(t)
    tadb = [[sum([w for t, w in tadb[i]]), i, set(tadb[i])]
            for i in tadb]      # build and filter transaction sets
    sall = sum([w for t, w in tracts])
    pexs = [i for s, i, t in tadb if s >= sall]
    tadb = [t for t in tadb if t[0] >= setts[1] and t[0] < sall]

    r = recurse(tadb, [], [], [], setts, store_handle)
    return r
# -----------------------------------------------------------------------


class FIStore:
    def __init__(self, setts):
        self.setts = setts
        self.supps = {}

    def add(self, cand):
        if ("max_var_s0" not in self.setts or len([c for c in cand[0] if c[0] == 0]) <= self.setts["max_var_s0"]) and \
           ("max_var_s1" not in self.setts or len([c for c in cand[0] if c[0] == 1]) <= self.setts["max_var_s1"]):
            self.supps[cand[0]] = cand[1]

    def getQueries(self):
        qs = []
        for cand, s01 in self.supps.items():
            q0 = tuple([c for c in cand if c[0] == 0])
            q1 = tuple([c for c in cand if c[0] == 1])
            if len(q0) > 0 and len(q1) > 0:
                s0 = self.supps.get(q0, -1)
                s1 = self.supps.get(q1, -1)
                if s0 > 0 and s1 > 0 and \
                    ("min_fin_in" not in self.setts or s01 >= self.setts["min_fin_in"]) and \
                        ("min_fin_acc" not in self.setts or s01/(s0+s1-s01) >= self.setts["min_fin_acc"]):
                    qs.append((q0, q1, s0, s1, s01))
        return qs


class CharbonXFIM(CharbonXaust):

    name = "XaustFIM"

    def isIterative(self):
        return False

    def computeExpansions(self, data, initial_terms):

        tracts = [[] for i in range(data.nbRows())]
        map_initc = [{}, {}]
        for i, c in enumerate(initial_terms):
            s, cid = c.getSide(), c.getCid()
            if cid not in map_initc[s]:
                map_initc[s][cid] = []
            k = (s, cid, len(map_initc[s][cid]))
            map_initc[s][cid].append(i)
            for rid in data.supp(s, c.getLit()):
                tracts[rid].append(k)
        tracts = [frozenset(t) for t in tracts]

        # target='s', supp=2, zmin=1, zmax=maxsize, out=0
        # maxx = zmax+1 if zmax < maxsize and target in 'cm' else zmax
        zmin = 1
        zmax = self.constraints.getCstr("max_var_s0") + self.constraints.getCstr("max_var_s1")
        min_supp = self.constraints.getCstr("min_itm_in")

        cs_setts = dict([(k, self.constraints.getCstr(k)) for k in ["max_var_s0", "max_var_s1",
                                                                    "min_fin_in", "min_fin_out", "min_fin_acc"]])

        cs = FIStore(cs_setts)
        r = mod_eclat(tracts, ['s', min_supp, zmin, zmax, zmax+1], cs.add)
        queries = cs.getQueries()
        cands = []
        for qs in queries:
            lits0 = [initial_terms[map_initc[0][q[1]][q[2]]].getLit().copy() for q in qs[0]]
            lits1 = [initial_terms[map_initc[1][q[1]][q[2]]].getLit().copy() for q in qs[1]]
            r = Redescription.fromQueriesPair([Query(False, lits0), Query(False, lits1)], data, copyQ=False)
            cands.append(r)
        return cands
