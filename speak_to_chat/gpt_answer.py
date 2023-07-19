import openai
import os

openai.api_key = os.getenv("GPT_API_KEY")

# gpt 모범 답변 튜닝 및 생성
def add_gptanswer(question, answer):
    prompt = []
    message = f"""Improve the answers to the following interview questions with better answers.\
        I will provide you with input forms including "question", "answer".\
        Look at the questions and answers below and make a better answer by correcting or adding any deficiencies in the answers\
        Don't change the content of the answer completely, but modify it to the extent that it improves.\
        Never say anything about the questions and answers below.\
        Don't write "Question" or "Answer"\
        Don't write about the question below.\
        Say it in Korean
        Question: `{question}`\
        Answer: `{answer}`"""

    prompt.append(
        {
            "role": "user",
            "content": message
        }
    )
    
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo", messages=prompt, temperature=0.7, n=1
    )

    message = completion.choices[0].message["content"]
    return message