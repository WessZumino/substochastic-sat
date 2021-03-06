#!/usr/bin/python

import sys
import numpy as np
from utilities import parseDAT, parseCNF


def makeDAT(datfile, files, optima, times):
    with open(datfile, 'w') as f:
        for i, file in enumerate(files):
            line = file + "   O = {0}   T = {1}\n".format(optima[i], times[i])
            f.write(line)


if __name__ == "__main__":

    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print "Usage: ./categorizeDAT.py <DAT> tag [bins]"
        sys.exit(1)

    datfile = sys.argv[1]
    tag = sys.argv[2]

    files, optima, times = parseDAT(datfile)

    if len(sys.argv) == 4:
        bins = int(sys.argv[3])
    else:
        bins = len(files)

    ratios = []

    for cnf in files:
        var, clauses = parseCNF(cnf)
        ratios.append(var/clauses)


    hist, edges = np.histogram(ratios, bins)

    avgs = (edges[1:] + edges[:-1])/2

    for i in range(len(hist)):
        if hist[i] > 0:
            if i == len(hist)-1:
                indices = np.flatnonzero(np.logical_and(ratios >= edges[i], ratios <= edges[i+1]))
            else:
                indices = np.flatnonzero(np.logical_and(ratios >= edges[i], ratios < edges[i+1]))
            datfile = tag + ".{0:.3f}.dat".format(avgs[i])

            selected_files = []
            selected_optima = []
            selected_times = []

            for j in indices:
                selected_files.append(files[j])
                selected_optima.append(optima[j])
                selected_times.append(times[j])
            print("Categorized {0} files under ratio {1} in DAT: {2}".format(len(selected_files), avgs[i], datfile))


            makeDAT(datfile, selected_files, selected_optima, selected_times)

