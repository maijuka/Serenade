
# SerenadeCS and SerenadeES instructions

This document provides instructions on how to run experiments with the SerenadeCS and SerenadeES algorithms.


## Setting up the environment
 
Make sure you have Python version at least 3.6, and you have installed at least scipy, numpy, matplotlib, scikit-learn, wxPython and cartopy 
OR 
you can create a pipenv using the given pipfile.


## Algorithm source code

mine_ES contains the source code for the SerenadeES algorithm.

mine_CS contains the source code for the SerenadeCS algorithm.

Both folders contain a file called **exec_clired.py**, which is used to run the algorithm. You don't need to edit any of the files in the mine_ES and mine_CS folders.


## Contents of the settings folders and files

To run the experiments correctly, you need to use a settings file that defines the parameters used by the algorithms.
There are two folders containing settings files, settings_CS and settings_ES, corresponding to the two algorithms.

Each settings file is named: settings_totalbudget_budgetdistribution.xml

Total budget is (0.5, 1, 10, 100) and the budget distribution is how the budget is divided to compute the initial pairs, extensions and quality. 
The distributions are the same as in the paper: d1 = (0.33, 0.33, 0.33), d2 = (0.45, 0.45, 0.1), d3 = (0.6, 0.3, 0.1), d4 = (0.3, 0.6, 0.1), and d5 = (0.25, 0.25, 0.5).

### Before running the experiments you need to edit the following parameters in all the settings files you want to use

* data_rep, path to the folder with the data
* LHS_data, insert the file name of the left hand side data
* RHS_data, same as above but for the right hand side data
* result_rep, folder where to save the experiment results

You can use the provided Python script **edit_settings.py**, to change these values for all settings files at once.

You can also change values for the parameters by hand:

```
<parameter>
	<name>LHS_data</name>
	<info>Complete filename for the left hand side data. (open text)</info>
	<value>data_LHS.csv</value>    <------- replace with the filename
</parameter>
```

The result filename is stored in **out_base**, and it currently tells the total budget (0.5, 1, 10, 100) and the budget distribution used to divide the budget to compute the initial pairs, extensions and quality. 
The distributions are the same as in the paper: d1 = (0.33, 0.33, 0.33), d2 = (0.45, 0.45, 0.1), d3 = (0.6, 0.3, 0.1), d4 = (0.3, 0.6, 0.1), and d5 = (0.25, 0.25, 0.5).

```
<parameter>
	<name>out_base</name>
	<info>Name of the file where to store the results. (open text)</info>
	<value>totalbudget_1_budgetdist_d4</value>     <--------- you can change this if you want to, but you don't need to
</parameter>
```

### Rest of the parameters are already set so that they match the name of the settings file

**You don't need to edit these**
* dp_budget = total budget used, values used in the paper are 0.5, 1, 10, 100
* dp_budget_init = ratio of the total budget used to compute the initial pairs
* dp_budget_ext = ratio of the budget to compute the extensions
* dp_budget_qual = ratio of the budget to compute the noisy quality 
* nb_init_pairs = number of initial pairs, set to 20
* nb_extension_rounds = number of times to extend the redescriptions, for ES it is 80, CS it is 4.
* age = the age parameter explained in the paper. Normally set to 40. Is not used for the CS experiments.
* log_k = the steepness parameter for the logistic function. Dependent on the dataset, for the mammals data it is 0.02.
* x0_ratio = parameter for the logistic function, ratio of the size of the dataset

Other parameters and their default values used for the mining can be found in the miner_confdef.xml file.


## Running the experiments

To start one run of either SerenadeCS or SerenadeES with one set of parameters, run the exec_clired.py file with a settings file.

The following will make one run of the SerenadeCS algorithm with total budget 1, and distribution (0.33, 0.33, 0.33):
**python ./mine_CS/exec_clired.py ./settings_CS/settings_1_d1.xml**

To run several experiments at once, you can use a shell script. There are two scripts provided **run_CS.sh** and **run_ES.sh**.

For example following script will run SerenadeCS with all settings files in the settings_CS folder.
```
for settings in ./settings_CS/*.xml;do
        pipenv run python ./mine_CS/exec_clired.py $settings &
done
```
