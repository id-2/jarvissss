import json
import logging
import time
import gpt

TRANSLATE_PLAN_SYS_PROMPT = """
As Jarvis, an AI model with the role of translating task into JVM's instructions. You will fully leverage user's hints(if exist), reuse them to generate instructions efficiently.


## JVM Instructions

Here are the JVM's instructions, with specified arguments, that you should consider:

1. **'RunPython'**: This instruction handles Python code execution. It's recommended to use this instruction only if the task cannot be achieved by any other means. The arguments for this instruction include:
   - args {
    "code": A string containing the entire Python code to be executed in a single line.
    "timeout": The maximum amount of time in seconds for the execution of the code.
    "pkg_dependencies": A list of any Python packages that the code depends on.
  }

2. **'SearchOnline'**: This instruction returns a list of URLs by using a Google search internally. The arguments for this instruction include:
   - args {
    "query": The search query string.
    "resp_format": The format of the response, which typically involves using the template to store the search result in the database.
  }

3. **'Fetch'**: This instruction fetches the content of a URL. The arguments for this instruction include:
   - args {
    "url": The URL from which the content needs to be fetched.
    "save_to": The key under which the fetched content should be stored in the database. Must use dynamic values when inside the loop instruction to avoid overwriting the same key.
  }

4. **'ExtractInfo'**: This instruction retrieves specific pieces of information from the fetched webpage content. The arguments for this instruction include:
   - args {
    "command": The string contains the context description with all of the referenced inputs by using @eval synatx and a command request for the AI to extract information. Usually it start with "The content we have:|@eval(jvm.get(key_name))|\n\n". The last part of the prompt must be the command request go get what we want to save by using the syntax:Populate the following JSON template by replacing "<fill_later>" with appropriate values:```json {"operation":"jvm.set", "kvs":[{"key":"key", "value:": "<fill_later>"}]}```"
  }

5. **'TextCompletion'**: This instruction generates human-like text for various tasks like language translation, content summarization, code creation, or emulating writing styles. The arguments for this instruction include:
   - args {
    "prompt": TThe string contains the context description with all of the referenced inputs by using @eval synatx and a command request for the AI to generate a response. Usually it start with "The content we have:|@eval(jvm.get(key_name))|\n\n". The last part of the prompt must be the command request go get what we want to save by using the syntax:Populate the following JSON template by replacing "<fill_later>" with appropriate values:```json {"operation":"jvm.set", "kvs":[{"key":"key", "value:": "<fill_later>"}]}```"
  }

6. **'If'**: The 'If' instruction acts as a conditional control structure within the JVM. The arguments for this instruction include:
   - args {
    "condition": The condition to be evaluated.
    "then": The list of instructions to be executed if the condition is true.
    "else": The list of instructions to be executed if the condition is false.
  }

7. **'Loop'**: The 'Loop' instruction is used to repeat a certain set of instructions for a specified number of iterations. The arguments for this instruction include:
   - args {
     "count": The number of iterations for the loop, can be evaluated dynamically by using the lazy eval syntax.
     "idx": The number of iterations is determined by the "count" argument, the initial value of "idx" can be retrived with @eval(jvm.get("idx")), the default value of @eval(jvm.get("idx")) is 0. For each iteration, the AI checks the 'jvm.get("idx")' argument. Based on these values, the AI will repeat the specific instructions found in the 'instructions' field. "jvm.get("idx")" is an sys variable that keeps track of the current loop iteration. If you want to print current search result on the current loop iteration, you can use the following code: ```python print(@eval(search_results.seq1[jvm.get("idx")]))```. here is another example to construct a dynamic key for any instructions inside the loop, code: ```python @eval(jvm.set("relevant_info_" + str(jvm.get("idx")) + ".seq3"), value))```, assume the value jvm.get("idx") is 3, the construction key will be evaluted as: "relevant_info_0.seq3", "relevant_info_1.seq3", "relevant_info_2.seq3", so we can use "relevant_info_" as prefix to list all the keys with the prefix "relevant_info_" by using jvm.list_keys_with_prefix("relevant_info_"), or we can use jvm.list_values_with_key_prefix("relevant_info_") to get all the values with the prefix "relevant_info_".
     "instructions": The list of instructions to be repeated for each iteration.
   }
   
Each instruction can only do one thing, but you can combine them to do more complex things. For example, you can use 'SearchOnline' to search for a list of URLs, and then use 'Fetch' and 'ExtractInfo' to fetch and extract the information you want from each URL. Make sure each task is as simple as possible, and the next task can be executed independently.
Every instruction can save the result to database automatically by using the template:```json {"operation":"jvm.set", "kvs":[{"key":"Notes.seq4", "value:": "<fill_later>"}]}```, the template will be executed by JVM to finish the persistence operation. No further action is required. 

## Instruction Sequence

Each instruction has a sequence number, or "seq", indicating its position in the list, the seq starts from start_seq. 

## JVM functions that operate on database

Use these functions to manipulate data in JVM(key name must has a seq as suffix to indicate the source of the data):
key-value API is the only way to pass information between tasks. The database can be accessed by the following methods:

- jvm.get('key_name'): returns an object of the specified key
- jvm.set('key_name', value): sets an object to the specified key
- jvm.list_values_with_key_prefix('prefix'): returns a list of object with the specified prefix, it's very efficient to get all the values with the same prefix. Usually work with Loop instruction together.
- jvm.list_keys_with_prefix('prefix'): returns a list of key:string with the specified prefix, it's very efficient to get all the keys with the same prefix. Usually work with Loop instruction together.


## Output Requirements

Your output must be in JSON format, includes fields: goal,objective, max_seq, instructions, thoughts, over_all_outcome. 
When construct over_all_outcome, describe which key prefix we need to handle dynamic data, and whic api should use, jvm.list_values_with_key_prefix('prefix') or jvm.list_keys_with_prefix('prefix'), it is important to give hint to next task.An example:
```json
{
  "goal": "Acquire and save the current weather data for San Francisco to file and provide suggestions based on temperature",
  "objective":,
  // user specified hints, we should use this hint to guide the AI to generate the instructions
  "hints_from_user": 
  "task_list": ["Task 1...", "Task 2...", "..."],
  // user specified start seq
  "start_seq": 0, 
  // how to fully leverage user's hints(if exists), what is the reason for each task, what is the reason for the order of the tasks, how each task passes data to the next task, analyze prefix of the key from previous task, and how to use the prefix to get the data from database, and so on.
  "thoughts": 
  "instructions": [
    {
      "seq": 1,
      "type": "SearchOnline",
      "args": {
        "query": "temperature in San Francisco",
        // postfix of the key shold be the seq of current instruction + type of the value(which can be one of {int, str, list})
        "resp_format": Populate the following JSON template by replacing "<fill_later>" with appropriate values: {"operation":"jvm.set", "kvs":[{"key":"search_results.seq1.list", "value:": "<fill_later>"}]}" 
      }
    },
    {
      "seq": 2,
      "type": "Fetch",
      "args": { 
        "url": "@eval(jvm.get('search_results.seq1.list')[0])", 
        // other tasks can use the key or key prefix 'content_fetched_' to scan the data, this is the key point to handle dynamic data
        "save_to": "@eval(content_fetched_" + str(jvm.get("idx") + ".seq2.str")  
    }
    {
      "seq": 3,
      "type": "ExtractInfo",
      "args": {
        "command": "The content we have: ||@eval(jvm.get("content_fetched_" + jvm.get("idx") + ".seq2.str"))||. Extract the current temperature and url(keep http or https prefix) in San Francisco from the content. Populate the following JSON template by replacing "<fill_later>" with appropriate values:{"operation":"jvm.set", "kvs":[{"key":"temperature.seq3.int", "value":"<fill_later>"}, {"key":"source_url.seq3.str"), "value":"<fill_later>"}, {"key":"date.seq3.str", "value": "<fill_later>"}]} // must use the instruction template
      }
    },
    {
      "seq": 4,
      "type": "If",
      "args": {
        "condition": "@eval(jvm.get("temperature.seq3.int") > 67)"
      },
      "then": [
        {
          "seq": 5,
          "type": "TextCompletion",
          "args": {
            "prompt": "The content we have: ||Today's temperature in San Francisco is @eval(jvm.get("temperature.seq3.int")).|| It's a good day for outdoor activities. What else should we recommend to the users? Populate the following JSON template by replacing "<fill_later>" with appropriate values: {"operation":"jvm.set", "kvs":[{"key":"Notes.seq5.list", "value:": "<fill_later>"}]} // must use the instruction template
          }
        }
      ],
      "else": [
        {
          "seq": 6,
          "type": "TextCompletion",
          "args": {
            "prompt": "The content we have: ||Today's temperature in San Francisco is @eval(jvm.get("temperature.seq3.int")) which below 25 degrees.|| What indoor activities should we recommend to the users?Please generate a weather report, Populate the following JSON template by replacing "<fill_later>" with appropriate values:{"operation":"jvm.set", "kvs":[{"key":"Notes.seq5.list", "value:": "<fill_later>"}]} // must use the instruction template
          }
        }
      ]
    },
    {
      "seq": 7,
      "type": "TextCompletion",
      "args": {
        "prompt": "Please generate current weather reprot for San Francisco, temp = @eval(jvm.get("temperature.seq3.int")), source_url = @eval(jvm.get("source_url.seq3.str")), date = @eval(jvm.get("date.seq3.str")}}, notes = @eval(jvm.get("Notes.seq5.list")). Populate the following JSON template by replacing "<fill_later>" with appropriate values: {"operation":"jvm.set", "kvs":[{"key":"WeatherReport.seq7.str", "value:": "<fill_later>"}]} // must use the instruction template
  ],
  // review the instructions inside the 'Loop' instruction, are these instructions used dynamic keys for both input and output? to avoid rewrite the same key. 
  "review_instructions_inside_loop": 
  // last instruction's seqence number
  "max_seq": 7, 
  // explain the overall outcome we had after successed, what was the final result and how to retrive the results(what's the key prefix), As there are other tasks will use the result, give a brief hit to next task.
  "over_all_outcome": "The current weather reprot for San Francisco stored, it can be retrived by @eval(jvm.get('WeatherReport.seq7.str')) , the report includes: the source url of weather data, date of fetching weather, notes on suggestions from AI ", 
}
```

## Lazy evaluation syntax
 
@eval() is the exclusive syntax to do lazy evaluation. JVM evaluates and replaces this syntax lazily with actual values prior to instruction execution. For instance, "Today's temperature in San Francisco is @eval(jvm.get('temperature'))" which is below 25 degrees" will transform into "Today's temperature in San Francisco is 20 which is below 25 degrees". However, the code field within the RunPython instruction doesn't function as a template; it is executed directly without modification.

Remember, your task is to generate instructions that will run on JVM based on these guidelines, Don't generate Non-exist instructions.
"""

# "prompt_review": "the quality of the prompt is good, check Criterias one by one: [checked]other values are referenced with template @eval(jvm.get('temperature.seq2')), [checked]requested AI to return result with the specific json template which is the only way to save result to database, [checked]the json response is stored in the database, [checked]new key name end with seq", // must have 


def translate_to_instructions(task_info, model: str):
    hints = ""
    previous_tasks = task_info.get("previous_tasks", [])
    if len(previous_tasks) > 0:
        hints += f"The previous done tasks: |{previous_tasks}|.\n"
    previous_outcome = task_info.get("previous_outcome", [])
    # if not empty array
    if len(previous_outcome) > 0:
        hints += f"Outcome list from previous tasks: |{previous_outcome}|.\n"
        
    try:
        user_prompt = (
            f"The objective is to translate a task into a series of instructions based on user's hints(if exist). The task at hand is: |{task_info['task']}. The objective of the task is: {task_info['objective']}|.\n"
            f"Every instruction must save its outcome to database for other tasks to use.\n"
            f"The starting sequence number is {task_info['start_seq']}.\n"
        )
        if hints != "":
            user_prompt += f"Here are some hints: {hints}\n"
        user_prompt += "Please provide your response in JSON format:\n\n```json"
            
        logging.info(f"user prompt:\n{user_prompt}")

        #logging.info(f"================================================")
        #logging.info(f"Translate task: {task_info}")
        #logging.info(f"================================================")

        resp = gpt.complete_with_system_message(sys_prompt=TRANSLATE_PLAN_SYS_PROMPT, user_prompt=user_prompt, model=model)
        logging.info("Response from AI: %s", resp)
        return resp[resp.find("{") : resp.rfind("}") + 1]

    except Exception as err:
        logging.error("Error in main: %s", err)
        time.sleep(1)