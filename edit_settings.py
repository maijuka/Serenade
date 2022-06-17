# -*- coding: utf-8 -*-

from xml.etree import ElementTree as et
import os

# name of the folder with the settings files
settings_folder = r"/settings_ES/" 
# folder where you want the experiment results
result_folder = "/results/"
# data folder
data_folder = "/data/"
# filename of the left hand side data
lhs_data = "data_LHS.csv"
# filename of the right hand side data
rhs_data = "data_RHS.csv"

  
for file in os.listdir(settings_folder):
    
        settingsfile = f"{settings_folder}/{file}"
        settings = et.parse(settingsfile)
        
        settings.find("./parameter/[name='data_rep']/value").text = data_folder
        settings.find("./parameter/[name='LHS_data']/value").text = lhs_data
        settings.find("./parameter/[name='RHS_data']/value").text = rhs_data
        settings.find("./parameter/[name='result_rep']/value").text = result_folder

        settings.write(settingsfile)