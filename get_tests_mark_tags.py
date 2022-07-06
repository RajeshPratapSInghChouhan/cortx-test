import re
from tools.clone_test_plan.jira_api import JiraTask

files = [".\\tests\\csm\\rest\\test_capacity_quota.py"]
# files = ["test_iam_users.py", "test_capacity_quota.py", "test_capacity_usage.py"]
test_list = []
skip_count = 0
# Iterate directory
for file_name in files:
    # check if current path is a file
    try:
        print("File ", file_name, " :")
        # opening and reading the file 
        file_read = open(file_name, "r")
        # string to be searched
        text_1 = "^class.*:$"
        text_2 = "@pytest.mark.skip"
        text_3 = "@pytest.mark.tags"
        skip_next = False
        lines = file_read.readlines()
        # looping through each line in the file
        for line in lines:
            x = re.search(text_1,line)
            if x:
                print("class : ",line)
            x = re.search(text_2,line)
            if x:
                print(line)
                skip_next = True
                skip_count = skip_count + 1
            x = re.search(text_3,line)
            if x:
                if skip_next:
                    print("this will be skipped",line)
                    skip_next = False
                    continue
                else:
                    # print(line)
                    line = line.split(".",2)[-1]
                    line = line.split("(",2)[1]
                    line = line.split(")",2)[0]
                    line = line.replace("'", '')
                    test_list.append(line)
                    print(line)

        # close file after reading
        file_read.close()
        print("test count : ", len(test_list))
        print("skip count : ", skip_count)
        print(test_list)
        jt = JiraTask()
        jt.add_tests_to_exist_te(test_list,"TEST-27330")

    except :
        print("\nThe file doesn't exist!")