import csv
import re
import logging
import subprocess


def demangle(name):
    """ 
    demangles function names, uses the demangle program
    rather than a demangle module since it isn't accessible on 
    some systems
    """
    command = ['c++filt']
    command.append( name )
    logging.debug(":processCsv:demangle c++ filt command {}<".format(command))
    pipes = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    std_out, std_err = pipes.communicate()

    if (pipes.returncode != 0):
        print("Error executing command {0}, return code {1}, exiting...".format(command, pipes.returncode))
        exit(1)

    # print("stdout {}".format(std_out.decode()))
    logging.debug(":processCsv:demangle stdout from demangle {}".format(std_out.decode()))
    demangled = std_out.decode().split("\n")

    if (demangled[0][:2] == "_Z"):
        print("Error, name was not demangled properly")
        print("Command used: {}".format(command))
        print("Result: {}". std_out.decode())

    # Each line ends with a newline, so the final entry of the split output
    # will always be ''.
    logging.debug(":processCsv:demangle demangled {}".format(demangled))
    assert len(demangled) == 2
    return demangled[0]

def convertUnits(data, units):
    """
    Takes data as a string converts them to a numerical value with no
    prefix. If the unit is unknown we try to convert to a numerical value
    """

    # units and their multipliers
    unitConversions = {'GB/s':1073741824, 'MB/s':1048576, 'KB/s':1024, 'B/s':1,
                         'ns':.000000001,   'us':.000001,   'ms':.001,   's':1}

    conversionFactor = 1
    if units not in unitConversions:
        logging.debug("Unknown unit, returning data as is")
    else:
        conversionFactor = unitConversions[units]
        logging.debug("Units: {} Conversion factor: {}".format(units, conversionFactor))
    try:
        value = float(data) * conversionFactor
    except:
        value = data

    logging.debug("Returned value: {}".format(value))
    return value

def processNvprofCSV(csvData, kernelMetrics = dict(), ignoreList = [], verbosePrint = False):
    """
    Processes a list of input strings that contains nvprof csv data and returns a dict of
    kernels with their metrics and data from those metrics
    Returns a dictionary of kernels, each kernel contains a dict with a list of metrics
    and a list of values for that metric ie:

                  dict        dict     list
    kernelMetrics[kernelName][metrics][data]

    If provided the kernelMetrics list must be in the same format and will be modified

    Positional arguments:
    csvData  -- the csv data to process, must be formatted as a list of lines with a header

    Keyword arguments:
    kernelMetrics -- a list of existing kernel metrics to append to (default: empty)
    ignoreList              -- a list of metrics or data in the input data to ignore (default: empty)
    verbose                         -- verbose mode (default: False)
    """

    nonDataLines = 0
    line = None
    try:
        line = csvData[nonDataLines]
    except IndexError:
        raise ValueError("Error loading datafile, data is empty: {}".format(csvData))
    except Exception:
        raise ValueError("Unkown error reading data {}\n{}".format(Exception,csvData))
    while not ("==" in line and "result:" in line):
        logging.debug("Consuming non-data line: {}".format(line))
        nonDataLines += 1

        # check to make sure that we haven't run out of data
        # its possible we may not have nvprof data
        if len(csvData) == nonDataLines:
            return kernelMetrics

        line = csvData[nonDataLines]

    nonDataLines += 1

    logging.info("Reached nvprof data")
    logging.debug("header: {0}".format(csvData[nonDataLines]))
    nvprof_reader = csv.DictReader(csvData[nonDataLines:])

    unitsRowRead = False
    for row in nvprof_reader:
        logging.debug("Processing row {}".format(row))

        if not unitsRowRead:
            units = row
            unitsRowRead = True
            continue

        # see what the name key is
        if "Kernel" in row.keys():
            kernelName = demangle(row["Kernel"])
            del row["Kernel"]
        elif "Name" in row.keys():
            kernelName = demangle(row["Name"])
            del row["Name"]
        else:
            raise KeyError("Unable to find Kernal name in csv data: {0}".format(row.keys()))

        kernelName = re.split(r'\[\d+\]', kernelName)[0].strip()
        logging.debug("Kernel {}".format(kernelName))

        # take all the stuff to ignore and delete it
        for item in ignoreList:
            if item in row:
                del row[item]

        # make sure we actually have a kernel name
        if len(kernelName) > 0:
            logging.debug("Checking kernel {}".format(kernelName))

            # add kernel if not there
            if kernelName not in kernelMetrics:
                logging.debug("Kernel {} not found adding to list".format(kernelName))

                kernelMetrics[ kernelName ] = {}

            #kernelMetrics[ kernelName ]["callCount"] += 1
            for key in row:
                if key not in kernelMetrics[ kernelName ]:
                    kernelMetrics[ kernelName ][ key ] = []
                kernelMetrics[ kernelName ][ key ].append(convertUnits(row[key], units[key]))

    # go through each kernel and get a call count
    for kernel in kernelMetrics:
        #print("kernel {} metrics {}".format(kernel, kernelMetrics[kernel]))
        firstKey = list(kernelMetrics[kernel].keys())[0]

        # get the lengtn of the first set of metrics
        count = len(kernelMetrics[kernel][firstKey])

        # sen the call count
        kernelMetrics[kernel][ "callCount" ] = count

        logging.debug("Callcount for {0}: {1:5}".format(kernel, count))


    return kernelMetrics
