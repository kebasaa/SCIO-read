Sys.setlocale("LC_ALL","English_United Kingdom")
Sys.setenv(TZ='UTC')
setwd("C:/Users/Jonathan/Documents/python/_scio_read")

import_json_nir<-function(filename){
    require(jsonlite)
    json_list<-fromJSON(filename)
    spectra_matrix<-matrix(unlist(json_list$records$spectrum),
                           nrow = json_list$header$num_records,
                           ncol = json_list$header$num_wavelengths,
                           byrow = TRUE)
    return(spectra_matrix)
}

import_json_nir('01_rawdata/scan_json/skin.json')