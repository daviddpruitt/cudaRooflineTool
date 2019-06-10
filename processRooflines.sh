#!/usr/bin/env bash

if [ "$#" -ne 3 ]
then
	echo "Usage ${0} <gnuplot template file> <directory with roofline data> <output directory>"
	exit
fi

template=$1
searchDir=$2
outputDir=$3

for csvFile in $searchDir/* 
do
	echo "Processing ${csvFile}"
	# get the file name without the extension
	strippedName=${csvFile##*/}
	strippedName=${strippedName%.csv}
	outputFile=${outputDir}/${strippedName}.gnu

	echo "Output file ${outputFile}"

	# for each file strip the last pause line
	head -n -1 $template > ${outputFile}

	# read a csv file
	echo '' >> ${outputFile}
	echo 'set datafile separator ","' >> ${outputFile}
	echo '' >> ${outputFile}
 	
	# add in the replot command
	echo "replot \"${csvFile}\" with xyerrorbars ls 1 notitle noenhanced \\" >> ${outputFile}
	echo "	,''	using 1:2:5 with labels rotate by 35 center offset 0, 1 notitle noenhanced" >> ${outputFile}
	echo "" >> ${outputFile} 

	# and the pause command
	echo 'pause -1 "hit any key to continue"' >> ${outputFile}
done
