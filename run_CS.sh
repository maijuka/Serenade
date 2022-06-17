for settings in ./settings_CS/*.xml;do
        pipenv run python ./mine_CS/exec_clired.py $settings &
done