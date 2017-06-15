#!/usr/bin/python

from optimizeLUT import parseLUT, sendEmail, getABounds, plotLUT, plotPsize, tryLUT
from scipy import stats
from subprocess32 import check_call, TimeoutExpired
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import fminbound
import datetime
import sys
from createLUT import makeLUT
from histAnalysis import parseOUT
from simanneal import Annealer

BOUND_CAP = 0.1  # cap on the bounds
BOUND_MULTIPLIER = 1.1  # fraction over which the bound can extend
UPDATE_PENALTY = 10000000  # penalty to give scripts which timeout
N_ITERS_CAP = 5  # max number of optimization iterations
RECURSION_LIMIT = 5  # max levels optimizer can branch LUT
THRESHOLD = 0.25  # min threshold before accepting new minimum


class Optimizer(Annealer):
    """Optimize using simulated annealing"""

    def __init__(self, var, state, other1, other2, tag, datfile, trials, plotenabled=False, verbose=False):
        self.other1, self.other2 = other1, other2
        self.tag = tag
        self.datfile = datfile
        self.trials = trials
        self.var = var
        self.forward = True
        self.plotenabled, self.verbose = plotenabled, verbose

        if var == "all":
            fullstate = state + other1 + other2
        else:
            fullstate = state
        super(Optimizer, self).__init__(fullstate)

    def move(self):
        """Perturb the current index randomly"""
        bins = len(self.other1)

        for row in range(bins):
            if self.var == "A":
                lbound, ubound = 0.1, 1.0
            elif self.var == "dT":
                lbound, ubound = 0.1, 100.0
            elif self.var == "psize":
                lbound, ubound = max([self.state[row]-4, 8]), self.state[row]+4
            else:
                self.state[row] = np.random.uniform(0.1, 100.0)  # perturb dT
                self.state[bins+row] = np.random.uniform(0.1, 1.0)  # perturb A
                self.state[bins+bins+row] = np.random.random_integers(max([self.other2[row]-4, 8]), self.other2[row]+4)  # perturb psize

                continue


            # perturb the given row
            self.state[row] = np.random.uniform(lbound, ubound)

            # # check bounds
            # self.state[self.row] = min([ubound, self.state[self.row]])
            # self.state[self.row] = max([lbound, self.state[self.row]])



    def energy(self):
        if self.var == "A":
            e = tryLUT(self.var, self.tag, self.datfile, self.trials, self.other1, self.state, self.other2,
                       plotenabled=self.plotenabled, verbose=self.verbose)
        elif self.var == "dT":
            e = tryLUT(self.var, self.tag, self.datfile, self.trials, self.state, self.other1, self.other2,
                       plotenabled=self.plotenabled, verbose=self.verbose)
        elif self.var == "psize":
            e = tryLUT(self.var, self.tag, self.datfile, self.trials, self.other1, self.other2, self.state,
                       plotenabled=self.plotenabled, verbose=self.verbose)
        else:
            bins = len(self.other1)

            e = tryLUT(self.var, self.tag, self.datfile, self.trials, self.state[:bins],
                       self.state[bins:(bins+bins)], self.state[(bins+bins):],
                       plotenabled=self.plotenabled, verbose=self.verbose)

        return e


def main():
    args = sys.argv
    email = False
    verbose = False
    plotenabled = False

    if '-m' in args:
        email = True
        args.remove('-m')
    if '-v' in args:
        verbose = True
        args.remove('-v')
    if '-p' in args:
        plotenabled = True
        args.remove('-p')
    if len(args) == 6 or len(args) == 8:
        global var
        var = args[1]

        lutfile = args[2]
        datfile = args[3]
        trials = args[4]
        tag = args[5]
        weight = None
        runtime = None

        if len(args) == 8:
            weight = args[6]
            runtime = args[7]

    else:
        print("Usage: ./annealer.py dT|A|psize|all [-v] [-m] [-p] <initialLUT> <filelist.dat> trials tag [\"step weight\" \"runtime\"]\n")
        return 1

    optimizeLUT(var, lutfile, datfile, trials, tag, weight, runtime, recursion_level=0, email=email, verbose=verbose, plotenabled=plotenabled)

    return 0


def optimizeLUT(var, lutfile, datfile, trials, tag, weight, runtime, recursion_level=0, email=False, verbose=False, plotenabled=False, start=datetime.datetime.now()):
    if recursion_level == 0:
        if plotenabled:
            # Turn on interactive plotting
            plt.ion()
        if verbose:
            print("########## STARTING OPTIMIZATION - " + datetime.datetime.now().strftime(
                "%a %d/%m/%y %H:%M:%S") + " ##########")

    # Load initial conditions for dT and A
    bins, dT, A, psize = parseLUT(lutfile)

    def printf(fval):
        if verbose:
            print("#################### Found new minimum: " + str(fval) + " ####################")
        if email:
            msg = "Found new minimum: " + str(fval)
            sendEmail(msg)

    # set initial minimum to initial LUT performance
    fmin = tryLUT(var, tag, datfile, trials, dT, A, psize, weight, runtime, plotenabled, verbose)

    if var == 'dT':
        varmin = dT.copy()
    elif var == 'A':
        varmin = A.copy()
    elif var == "psize":
        varmin = psize.copy()
    elif var == "all":
        pass
    else:
        raise Exception("Invalid variable argument! Must be \"dT\", \"A\", \"psize\" or \"all\"")

    if var != "all":

        if var == "dT":
            varvector, other1, other2 = dT, A, psize
        elif var == "A":
            varvector, other1, other2 = A, dT, psize
        else:
            varvector, other1, other2 = psize, dT, A

        opt = Optimizer(var, varvector.tolist(), other1, other2, tag, datfile, trials, plotenabled, verbose)

        # the state vector can simply be copied by slicing
        opt.copy_strategy = "slice"

        opt.Tmax = 5000000/float(trials)  # Max (starting) temperature
        opt.Tmin = 100000/float(trials)      # Min (ending) temperature
        opt.steps = 1000   # Number of iterations

        vlist, fval = opt.anneal()

        varvector[:] = vlist[:]



    else:
        varvector, other1, other2 = dT, A, psize

        opt = Optimizer(var, varvector.tolist(), other1.tolist(), other2.tolist(), tag, datfile, trials, plotenabled, verbose)

        # the state vector can simply be copied by slicing
        opt.copy_strategy = "slice"

        opt.Tmax = 5000000/float(trials)  # Max (starting) temperature
        opt.Tmin = 100000/float(trials)      # Min (ending) temperature
        opt.steps = 1000   # Number of iterations

        vlist, fval = opt.anneal()

        varvector[:] = vlist[:bins]
        other1[:] = vlist[bins:(bins+bins)]
        other2[:] = vlist[(bins+bins):]


    if fval < fmin:
        fmin = fval

        _, _, _, best_updates = parseOUT(tag + ".out")

        varmin = varvector.copy()

        printf(fmin)

        # Store the best var
        lut = tag + ".OPTIMAL." + var + ".lut"
        if var == "dT":
            makeLUT(lut, bins, varmin, A, psize)
        elif var == "psize":
            makeLUT(lut, bins, dT, A, varmin)
        else:
            makeLUT(lut, bins, dT, varmin, psize)

        if plotenabled:
            plt.savefig(tag + ".OPTIMAL." + var + ".png")


    if var == "both":
        lut = tag + ".lut"
        fmin, dT, A = branchLUT(lut, tag, datfile, trials, weight, runtime, recursion_level, email, plotenabled, verbose, start)
    elif var == 'A':
        A = varmin.copy()
    elif var == 'psize':
        psize = varmin.copy()
    else:
        dT = varmin.copy()

    if recursion_level == 0:
        if verbose:
            # Print the best updates
            print("Best # updates: " + str(fmin))
        if plotenabled:
            if var == "psize":
                plotPsize(dT, psize)
            else:
                plotLUT(dT, A)
        if email:
            if var == "both":
                msg = "Optimization finished after " + str(datetime.datetime.now() - start) + \
                      ", at " + datetime.datetime.now().strftime("%a %d/%m/%y %H:%M:%S") + \
                      "!\nOptimal dT: {0}\nOptimal A: {1}\nOptimum # updates: {2}\n".format(dT, A, fmin)
            else:
                msg = "Optimization finished after " + str(datetime.datetime.now() - start) + \
                      ", at " + datetime.datetime.now().strftime("%a %d/%m/%y %H:%M:%S") + \
                      "!\nOptimal " + var + ": " + str(varmin) + "\nOptimum # updates: " + str(fmin) + "\n"
            sendEmail(msg)

    return fmin, dT, A, psize


def getMinimizer(var):
    # Minimize var
    if var == 'dT':
        if xpmt == 1:
            def f(edge, edgeI, tag, filename, trials, dT, A, psize, weight, runtime, p=False, v=False):
                edges = np.insert(np.cumsum(dT), 0, 0)

                edges[edgeI + 1] = edge

                dT = np.diff(edges)

                return tryLUT(tag, filename, trials, dT, A, psize, weight, runtime, p, v)
        else:
            f = lambda x1, i, x2, a1, a2, a3, a4, psize, a5, a6, v, p: tryLUT(a1, a2, a3, np.insert(x2, i, x1),
                                                                              a4, psize, a5,
                                                                              a6, verbose=v,
                                                                              plotenabled=p)  # rearranging the arguments for dT
    elif var == 'A':
        f = lambda x1, i, x2, a1, a2, a3, a4, psize, a5, a6, v, p: tryLUT(a1, a2, a3, a4, np.insert(x2, i, x1), psize, a5,
                                                                          a6, verbose=v,
                                                                          plotenabled=p)  # rearranging the arguments for A
    elif var == 'both':
        return None
    elif var == 'psize':
        f = lambda x1, i, x2, a1, a2, a3, a4, a5, a6, a7, v, p: tryLUT(a1, a2, a3, a4, a5, np.insert(x2, i, x1), a6, a7,
                                                                       verbose=v, plotenabled=p)
    else:
        raise Exception("Invalid variable argument! Must be \"dT\", \"A\" or \"both\"")
    return f


def branchLUT(lut, tag, datfile, trials, weight, runtime, recursion_level, email, plotenabled, verbose, start):
    # Get the best var
    bins, dT, A, psizes = parseLUT(lut)
    # split dT's largest bin in half
    maxBin = dT.max()
    maxI = dT.argmax()
    dT[maxI] = maxBin / 2.0
    dT = np.insert(dT, maxI, maxBin / 2.0)
    A = np.insert(A, maxI, A[maxI])
    psizes = np.insert(psizes, maxI, psizes[maxI])

    lut = lut.rstrip(".lut") + "." + str(recursion_level) + ".lut"

    if verbose:
        print("###########################################################")
        print("###########################################################")

    makeLUT(lut, bins + 1, dT, A, psizes)

    if verbose:
        print("Recursing down to level {0}...".format(recursion_level + 1))
        print("dT={0}\nA={1}".format(dT, A))
    if email:
        msg = "Recursing down to level {0}...".format(recursion_level+1)
        sendEmail(msg)

    return optimizeLUT("both", lut, datfile, trials, tag, weight, runtime, recursion_level=recursion_level + 1,
                       email=email, verbose=verbose, plotenabled=plotenabled, start=start)


if __name__ == "__main__":
    sys.exit(main())
