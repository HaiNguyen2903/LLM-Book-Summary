# About the Application
The application enables users to upload their own PDF books and automatically generate high-quality summaries and insights from the original text, helping them quickly extract key information and value from their reading material.

![My Image](images/demo_1.png)

# Installation Guidline

## Create a conda environment:
```
conda create -n {your environment}
```

## Activate the created environment:
```
conda activate {your environment}
```

## Install neccessary packages:
```
pip install -r requirements.txt
```

## Clone this project
To clone this project, run:
```
git clone https://github.com/HaiNguyen2903/LLM-Book-Summary
```

Move to the repo folder:
```
cd LLM-Book-Summary
```

## Export API key to local environment
In order to use OpenAI API key, activate your virtual enviroment and run the following script:
```
export OPENAI_API_KEY="YOUR_API_KEY"
```

# Run the application
In order to run the streamlit app, run:
```
streamlit run app.py
```