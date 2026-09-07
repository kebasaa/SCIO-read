# Calibration deemed necessary if:
# - 1 day passed
# - X nb scans done
# - abs(T difference) between sample and calibration is >


Base URL: https://api.consumerphysics.com/v



The only way to get the raw data is scanning using the app and exporting the data via SCiOlab web application.

Once you export the data, you will get a CSV file with the raw data divided into three “batches”: Spectrum, wr_raw and sample_raw.

The first batch of scans is the reflectance spectrum (R) – how much of the light is reflected back by the sample. The second batch is the raw signal from the sample (S), and the third is the raw signal from the calibration (C).

In order to calculate reflectance we use this formula: R=S/C.









SCiO includes a light source that illuminates the sample and an optical sensor called a spectrometer that collects the light reflected from the sample.



The spectrometer breaks down the light to its spectrum (the spectra), which includes all the information required to detect the result of this interaction between the illuminated light and the molecules in the sample. This means that SCiO analyses the overall spectra that is received and, comparing it to different algorithms and information provided, identifies or evaluates it.



For example, if you know the basic spectra of a watermelon, and then see that as the watermelon gets sweeter, meaning it has more sugar content, the spectra gradually changes in a specific manner, you will be able to build an algorithm in accordance.



In recognizing the existence of a specific material, such as ginger, in a sample, you will need to see if the reflectance of the material changes in a specific manner when the ginger is present.  Thus, you will need two samples of the material – with and without ginger.



The basic idea is that we look at the overall reflectance and the why it changes – we do not separate and analyse it per specific molecules, rather we look at the whole composition.



This is why if your chemical composition varies between samples significantly and not only because of the factor you wish to analyse, you will need more samples, as with saliva.



We suggest you check out  and  for further information on spectroscopy.



Specifically, as for tomatoes, 40 is the amount of samples that we mention as a rule of thumb as a properly sized collection for a feasibility test. However, a comprehensive application should be based on hundreds of samples and thousands of scans.
