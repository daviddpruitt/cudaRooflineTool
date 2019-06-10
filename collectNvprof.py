#!/usr/bin/env python3

import subprocess
import sys
import csv
import logging
import statistics
import os
import re

from processCsvData import *

nvMetricNames = ["flop_count_dp",
                 "flop_count_sp",
                 "flop_count_hp",
                 "gld_throughput",
                 "gst_throughput",
                 "local_load_throughput",
                 "local_store_throughput",
                 "shared_load_throughput",
                 "shared_store_throughput",
                 "l2_read_throughput",
                 "l2_write_throughput",
                 "dram_read_throughput",
                 "dram_write_throughput"]

# these are the throughput metrics,
# we use these to convert throughput
# to counts
throughputMetrics = ["gld_throughput",
                     "gst_throughput",
                     "g_throughput",
                     "local_load_throughput",
                     "local_store_throughput",
                     "local_throughput",
                     "shared_load_throughput",
                     "shared_store_throughput",
                     "shared_throughput",
                     "l2_read_throughput",
                     "l2_write_throughput",
                     "l2_throughput",
                     "dram_read_throughput",
                     "dram_write_throughput",
                     "dram_throughput"]

countMetrics = ["gld_bytes",
                "gst_bytes",
                "g_bytes",
                "local_load_bytes",
                "local_store_bytes",
                "local_bytes",
                "shared_load_bytes",
                "shared_store_bytes",
                "shared_bytes",
                "l2_read_bytes",
                "l2_write_bytes",
                "l2_bytes",
                "dram_read_bytes",
                "dram_write_bytes",
                "dram_bytes"]

# map of metric names to readable names
metricNames = {"flop_count_dp"         :"dp flops",
               "flop_count_sp"         :"sp flops",
               "flop_count_hp"         :"hp flops",
               "gld_throughput"        :"global load throughput",
               "gst_throughput"        :"global store throughput",
               "g_throughput"          :"global memory throughput",
               "local_load_throughput" :"local load throughput",
               "local_store_throughput":"local store throughput",
               "local_throughput"      :"local memory throughput",
               "shared_load_throughput":"shared load throughput",
               "shared_load_throughput":"shared store throughput",
               "shared_throughput"     :"shared memory throughput",
               "l2_read_throughput"    :"l2 read throughput",
               "l2_read_throughput"    :"l2 write throughput",
               "l2_throughput"         :"l2 memory throughput",
               "dram_read_throughput"  :"memory read throughput",
               "dram_write_throughput" :"memory write throughput",
               "dram_throughput"       :"memory memory throughput",
               "gld_bytes"             :"global loads",
               "gst_bytes"             :"global stores",
               "g_bytes"               :"global memory",
               "local_load_bytes"      :"local loads",
               "local_store_bytes"     :"local stores",
               "local_bytes"           :"local memory",
               "shared_load_bytes"     :"shared loads",
               "shared_store_bytes"    :"shared stores",
               "shared_bytes"          :"shared memory",
               "l2_read_bytes"         :"l2 reads",
               "l2_write_bytes"        :"l2 writes",
               "l2_bytes"              :"l2 memory",
               "dram_read_bytes"       :"memory reads",
               "dram_write_bytes"      :"memory writes",
               "dram_bytes"            :"memory"}

combinedMetrics = {"g_throughput":      ["gld_throughput", "gst_throughput"],
                   "local_throughput":  ["local_load_throughput", "local_store_throughput"],
                   "shared_throughput": ["shared_load_throughput", "shared_store_throughput"],
                   "l2_throughput":     ["l2_read_throughput", "l2_write_throughput"],
                   "dram_throughput":   ["dram_read_throughput", "dram_write_throughput"]}

# the metrics used for rooflines, along with their names
rooflineMetricsFlops = ["flop_count_dp",
                        "flop_count_sp",
                        "flop_count_hp"]

rooflineMetricsMem = ["shared_bytes",
                      "l2_bytes",
                      "dram_bytes"]

flopsMultipliers = {"flop_count_dp" : 1,
                    "flop_count_sp" : 2,
                    "flop_count_hp" : 4}

rooflineMetrics = ["flop_count_dp",
                   "flop_count_sp",
                   "flop_count_hp",
                   "s_bytes",
                   "l2_bytes",
                   "dram_bytes",
                   "gld_throughput",
                   "gst_throughput",
                   "g_throughput",
                   "g_bytes",
                   "local_load_throughput",
                   "local_store_throughput",
                   "local_throughput",
                   "local_bytes",
                   "shared_load_throughput",
                   "shared_store_throughput",
                   "s_throughput",
                   "s_bytes",
                   "l2_read_throughput",
                   "l2_write_throughput",
                   "l2_throughput",
                   "l2_bytes",
                   "dram_read_throughput",
                   "dram_write_throughput",
                   "dram_throughput",
                   "dram_bytes"]

def formatKernel(stringToStrip):
    # strip out parameter list
    stringToStrip = str.split(stringToStrip, '(')[0]

    # get rid of variable types
    types = re.compile('(void|bool|char|short|int|long|float|double)')
    stringToStrip = types.sub('', stringToStrip)

    # get rid of symbols that will cause issues
    parens = re.compile('(<|>|\(|\)| |,|=|\*)')
    newString = parens.sub('_', stringToStrip)
    stringToStrip = newString
    underscores = re.compile('(__|___|____|_____)')
    newString = underscores.sub('_', stringToStrip)
    stringToStrip = newString
    newSTring = underscores.sub('_', stringToStrip)

    return newString

def FormatUnits(value, baseTwo=False, baseUnit=''):
    """
    Takes a given value and formats it in a human readable form
    supports base two and base ten
    Examples:
    value = 4096 return 4k
    value = 4096 baseTwo = false return 4.096k
    value = 4096 baseTwo = false baseUnit = "B/s" return 4.096kB/s
    """

    prefixes = ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']
    divisor = 1000
    if baseTwo:
        divisor = 1024

    for prefix in prefixes:
        if value < divisor:
            return "{:.3f} {}{}".format(value, prefix, baseUnit)
        value = value / divisor

    return "{:.3f}Y{}".format(value, prefix, baseUnit)

def ProfileApp(command):
    """
    Profiles a given cuda application using the command provided
    The profile data is returned as a dict of kernels with their metrics
    and the data for each call
    """

    logging.info("Command to profile: {0}".format(" ".join(command)))

    kernelMetrics = dict()

    # get execution time first because for whatever reason
    # we need a different nvprof command
    # build the profiling command
    profileCommand = ["nvprof", "--print-gpu-trace", "--csv"]
    profileCommand.extend(command)

    logging.info("nvprof command: {0}".format(" ".join(profileCommand)))

    # setup so we capture stdout and stderr and run the command
    pipes = subprocess.Popen(profileCommand, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    std_out, std_err = pipes.communicate()

    if (pipes.returncode != 0):
        print("Error executing command {0}, return code {1}, exiting...".format(profileCommand, pipes.returncode))
        exit(1)

    logging.debug("nvprof output")
    logging.debug("{0}".format(std_err.decode()))
    # take our output and store it in our dictionary of metrics
    processNvprofCSV(std_err.decode().splitlines(), kernelMetrics)

    for metric in nvMetricNames:
        std_out = ""
        std_err = ""

        # build the profiling command
        profileCommand = ["nvprof", "--metrics", metric, "--print-gpu-trace", "--csv"]
        profileCommand.extend(command)

        logging.info("nvprof command: {0}".format(" ".join(profileCommand)))

        # setup so we capture stdout and stderr and run the command
        pipes = subprocess.Popen(profileCommand, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        std_out, std_err = pipes.communicate()

        if (pipes.returncode != 0):
            print("Error executing command {0}, return code {1}, exiting...".format(profileCommand, pipes.returncode))
            exit(1)

        # take our output and store it in our dictionary of metrics
        processNvprofCSV(std_err.decode().splitlines(), kernelMetrics)

    return kernelMetrics

def generateDerivedMetrics(kernelMetrics, statistics, throughputMetrics = {}, countMetrics = {}, combinedMetrics = {}):
    """
    Takes a set of metrics and adds a set of derived metrics
    A given set of throughput metrics will be converted to its equivalent 
    counts using the duration given in statistics
    Metrics from combined metrics will then be summed together to generate
    a new combined metric
    """

    # combine single metrics 
    for combinedMetric in combinedMetrics:
        for kernel in kernelMetrics:
            logging.debug("Combining metrics for kernel {}".format(kernel))
            # iterate over each run, take the number of runs to be
            # the length of the first source metric
            if combinedMetrics[combinedMetric][0] in kernelMetrics[kernel]:
                combinedMetricCounts = []
                sourceMetricMissing = False
                # go through each run
                for run in range(0, len(kernelMetrics[kernel][ combinedMetrics[combinedMetric][0] ])):

                    combinedMetricRunCount = 0
                    # take all the source metrics and add them into the
                    # combined metric
                    for sourceMetric in combinedMetrics[combinedMetric]:
                        if sourceMetric in kernelMetrics[kernel]:
                            # TODO delete once debugged print("runs of {} {}".format(sourceMetric, kernelMetrics[kernel][sourceMetric]))
                            combinedMetricRunCount = combinedMetricRunCount +  kernelMetrics[kernel][sourceMetric][run]
                        else:
                            sourceMetricMissing = True
                            logging.info("Source metric {} missing for combined metric {}, combined metric will not be"
                                         "added".format(sourceMetric, combinedMetric))
                    # append this run ot the end of the list
                    combinedMetricCounts.append(combinedMetricRunCount)
                if not sourceMetricMissing:
                    kernelMetrics[kernel][combinedMetric] = combinedMetricCounts

    # take throughputs and convert them to counts
    # doesn't use averages since that can skew results
    for throughputMetricName, countMetricName in zip(throughputMetrics, countMetrics):
        for kernel in kernelMetrics:
            logging.debug("Generating count metrics for {} in kernel {}".format(throughputMetricName, kernel))
            if throughputMetricName in kernelMetrics[kernel]:
                counts = []
                for run in range(0, len(kernelMetrics[kernel][throughputMetricName])):
                    count = kernelMetrics[kernel][throughputMetricName][run] * kernelMetrics[kernel]["Duration"][run]
                    counts.append(count)
                kernelMetrics[kernel][countMetricName] =  counts

def generateRooflinePoints(kernelMetrics):
    """
    Generates roofline points from a set of kernel metrics
    The flops type is automatically selected to be the one
    with the highest throughput
    """

    rooflines = dict()

    # one point for each kernel
    # runs are averaged
    for kernel in kernelMetrics:
        # figure out which flops is highest
        flops = dict()
        for flopsMetric in rooflineMetricsFlops:
            if flopsMetric in kernelMetrics[kernel]:
                flops[flopsMetric] = statistics.mean(kernelMetrics[kernel][flopsMetric]) * flopsMultipliers[flopsMetric]

        if len(flops) == 0:
            continue

        flopsMetric = max(flops, key=flops.get)

        durationList    = kernelMetrics[kernel]["Duration"]
        flopsList       = kernelMetrics[kernel][flopsMetric]
        # really should use numpy for this but some systems don't have it installed
        flopsPerSecList = [flops / duration for flops, duration in zip(flopsList, durationList)]

        #[flops / duration for flops, duration in zip

        # calculate intensity for each memory type
        # and add it to the list
        for memMetric in rooflineMetricsMem:
            if memMetric in kernelMetrics[kernel]:
                #intensity = flops / statistics.mean(kernelMetrics[kernel][memMetric])
                intensityList = [flops / data for flops, data in  zip (flopsList, kernelMetrics[kernel][memMetric])]
                #intensityList = flopsList / np.array(kernelMetrics[kernel][memMetric])
                kernelName = metricNames[memMetric] + " " + kernel

                intensityStdDev = 0
                flopsPerSecStdDev = 0
                if len(intensityList) > 1:
                    intensityStdDev = statistics.stdev(intensityList)
                    flopsPerSecStdDev = statistics.stdev(flopsPerSecList)

                rooflines[kernelName] = [statistics.mean(intensityList),  statistics.mean(flopsPerSecList),
                                         intensityStdDev, flopsPerSecStdDev]

    return rooflines

def generateAspenModel(kernelMetrics, modelName=None, rooflines=None):
    """
    Generates and aspen model based on kernel metrics
    counts will be based on profile data
    """

    # metrics we care about and the mapping to aspen resources
    aspenMetricsFlops = {"flop_count_dp" : "as dp",
                         "flop_count_sp" : "as sp"}

    aspenMetricsMem = {"dram_read_bytes"    : "loads",
                       "dram_bytes"         : "stores",
                       "l2_read_bytes"      : "loads_l2", 
                       "l2_write_bytes"     : "stores_l2",
                       "shared_load_bytes"  : "loads_shared",
                       "shared_store_bytes" : "stores_shared"}

    if modelName is None:
        raise ValueError("Error, no modelname for aspen model given")

    if modelName == "":
        raise ValueError("Error, the modelname can't be blank")

    indent = 0
    modelFileName = modelName + ".aspen"

    with open(modelFileName, 'w') as aspenFile:
        # boilerplate
        aspenFile.write("// Aspen file generated automatically using cuda roofline tool\n")
        aspenFile.write("// All kernels have exact counts from profiling\n")
        aspenFile.write("// This model needs to know the number of processors to run on\n")
        aspenFile.write("\n\n")

        aspenFile.write("model {} {{\n".format(modelName))

        indent = indent + 1
        aspenFile.write("{}param numThreads = numProcessors\n".format("\t" * indent))

        # write out the individual kernel calls
        for kernel in kernelMetrics:
            # ignore library calls (usually start with [)
            if kernel[0] == "[":
                continue

            # first some kernel info
            aspenFile.write("{}// kernel {} average exec time {}\n".format("\t" * indent, formatKernel(kernel),
                  statistics.mean(kernelMetrics[kernel]["Duration"])))
            if rooflines:
                aspenFile.write("{}// roofline points\n".format("\t" * indent))
                for roofline in rooflines:
                    if kernel in roofline:
                        aspenFile.write("{}// {} flops/byte {}  gflops\n".format("\t" * indent,
                           rooflines[roofline][0], rooflines[roofline][1] / 1.0e09))

            aspenFile.write("{}kernel {} {{\n".format("\t" * indent, formatKernel(kernel)))
            indent = indent + 1

            aspenFile.write("{}execute [ {} ] {{\n".format("\t" * indent, kernelMetrics[kernel]["callCount"]))
            indent = indent + 1

            # flops first
            for flopMetric in aspenMetricsFlops:
                if flopMetric in kernelMetrics[kernel]:
                    aspenFile.write("{}flops [ {} / numThreads ] {}\n".format("\t" * indent,
                        statistics.mean(kernelMetrics[kernel][flopMetric]), aspenMetricsFlops[flopMetric]))

            aspenFile.write("\n")

            # memory next
            for memMetric in aspenMetricsMem:
                if memMetric in kernelMetrics[kernel]:
                    aspenFile.write("{}{} [ {} / numThreads]\n".format("\t" * indent,
                        aspenMetricsMem[memMetric], statistics.mean(kernelMetrics[kernel][memMetric])))

            # close out kernels
            indent = indent - 1
            aspenFile.write("{}}}\n".format("\t" * indent))

            indent = indent - 1
            aspenFile.write("{}}}\n\n".format("\t" * indent))

        # do the main kernel
        aspenFile.write("{}kernel main {{\n".format("\t" * indent))
        indent = indent + 1

        # calls to all of the kernels
        for kernel in kernelMetrics:
            # skip library calls
            if kernel[0] == "[":
                continue
            aspenFile.write("{}call {}()\n".format("\t" * indent, formatKernel(kernel)))

        indent = indent - 1
        aspenFile.write("{}}}\n".format("\t" * indent))

        # end of the model
        aspenFile.write("}\n")

def generateRooflinesCSV(rooflines, kernelMetrics, modelName):
    for kernel in kernelMetrics:
        for roofline in rooflines:
            if kernel in roofline:
                csvFileName = modelName + "_" + formatKernel(kernel) + ".csv"
                with open(csvFileName, 'a', newline='') as csvfile:
                    csvfile.write("{},{},{},{},{}\n".format(rooflines[roofline][0], rooflines[roofline][1] / 1.0e9,
                                                            rooflines[roofline][2], rooflines[roofline][2] / 1.0e9, formatKernel((roofline)[:25])))

logging.basicConfig(level=logging.INFO)

if len(sys.argv) < 2:
    print("Correct usage {0} <command to profile>".format(sys.argv[0]))
    exit(0)

command = sys.argv[1:]

kernelMetrics = ProfileApp(command)

print("List of kernels")
for kernel in kernelMetrics:
    print("{0}".format(kernel))

#print("Kernel metrics")
#for kern in kernelMetrics:
#        print("{0} {1}".format(kern, list(kernelMetrics[kernel].keys())))
#        print("{0}".format(kernelMetrics[kern]))

generateDerivedMetrics(kernelMetrics, statistics, throughputMetrics, countMetrics, combinedMetrics)

rooflines = generateRooflinePoints(kernelMetrics)

aspenModelName = os.path.basename(sys.argv[1])
generateAspenModel(kernelMetrics, aspenModelName, rooflines)

for kernel in kernelMetrics:
    duration = statistics.mean(kernelMetrics[kernel]["Duration"])
    print("Kernel {} Duration {}".format(kernel, duration))
    for metric in rooflineMetrics:
        if metric in kernelMetrics[kernel]:
            print("{} {}".format(metric, FormatUnits(statistics.mean(kernelMetrics[kernel][metric]))))
    for metric in metricNames:
        if metric in kernelMetrics[kernel]:
            print("{}".format(FormatUnits(statistics.mean( kernelMetrics[kernel][metric] ), baseUnit=metric + "/s")))


generateRooflinesCSV(rooflines, kernelMetrics, aspenModelName)
print("Roofline points")
for kernel in rooflines:
    print("{}  {}  flops/byte  {}  flops/sec".format(kernel, rooflines[kernel][0], rooflines[kernel][1]))

