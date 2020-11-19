folders=("common" "env" "player/red")

for folder in ${folders[@]};
do 
  find $folder -name "*.py" | xargs autopep8 --in-place --aggressive
done