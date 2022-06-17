for settings in ./settings_ES/*.xml;do
        pipenv run python ./mine_ES/exec_clired.py $settings &
done