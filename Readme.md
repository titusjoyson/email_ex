Email Ex
========

**Before start executing the project please read the billow**

Description
-----------

This project contains two scripts `fetch_gmail.py` and `api.py`. The `fetch_gmail.py` allows you to fetch the data from users email account and store them in SqLite database, `api.py` allows users to do modifications on the fetched email.


Installing and configuring
--------------------------

**Creating a virtual env with python 3 is highly recommended**

* Install packages:

	```shell
	$ pip install -r requirement.txt
	```

* Enable the Gmail API

	* Navigate to the following link and enable Gmail api and download the `credentials.json` file and place it inside the project directory. [click here](https://developers.google.com/gmail/api/quickstart/python)


Executing
---------

* First run the file `fetch_gamil.py`
	
	```shell
	$ python fetch_gmail.py
	```

* Second run the file `api.py`
	
	```shell
	$ python api.py
	```

Api Details
-----------

* You can find the api details in the following postman collection link, [click here](https://www.getpostman.com/collections/07c8cc2f407f4bc710ff)

	https://www.getpostman.com/collections/07c8cc2f407f4bc710ff