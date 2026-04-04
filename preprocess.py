import json
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.exceptions import OutputParserException
from llm_helper import llm


def process_posts(raw_file_path, processed_file_path="data/processed_posts.json"):
    enriched_posts = []
    with open(raw_file_path, encoding='utf-8') as file:
        posts = json.load(file)
        for post in posts:
            metadata = extract_metadata(post['text'])
            # merge dictionaries (requires Python 3.9+)
            posts_with_metadata = post | metadata
            enriched_posts.append(posts_with_metadata)
  
    unified_tags = get_unified_tags(enriched_posts)

    for post in enriched_posts:
        current_tags = post.get('tags', [])
        # guard: ensure it's a list
        if not isinstance(current_tags, list):
            current_tags = list(current_tags)
        # use mapping.get(tag, tag) to avoid KeyError if mapping misses an original tag
        new_tags = {unified_tags.get(tag, tag) for tag in current_tags}
        post['tags'] = list(new_tags)
    
    with open(processed_file_path, encoding='utf-8', mode="w") as outfile:
        json.dump(enriched_posts, outfile, indent=4)


def get_unified_tags(posts_with_metadata):
    unique_tags = set()
    for post in posts_with_metadata:
        tags = post.get('tags', [])
        if isinstance(tags, (list, set, tuple)):
            unique_tags.update(tags)
        else:
            unique_tags.add(str(tags))

    unique_tags_list = ', '.join(sorted(unique_tags))

    # Note: explicitly list 'tags' as the only input variable so langchain won't try to auto-detect variables
    template = '''I will give you a list of tags. You need to unify tags with the following requirements:
1. Merge similar tags into a shorter unified list. Examples:
   - Jobseekers, Job Hunting -> Job Search
   - Motivation, Inpiration, Drive -> Motivation
   - Personal Growth, Personal Development, Self Improvement -> Self Improvement
   - Scam Alert, Job Scam -> Scams
2. Each output tag must follow Title Case (e.g. "Job Search").
3. Output only a JSON object (no explanation or preamble).
4. The JSON object should map each original tag to its unified tag. Example:
   {{"Jobseekers": "Job Search", "Job Hunting": "Job Search", "Motivation": "Motivation"}}

Here is the list of tags:
{tags}
'''
    # IMPORTANT: tell PromptTemplate which variables are expected
    pt = PromptTemplate(template=template, input_variables=['tags'])
    chain = pt | llm

    response = chain.invoke(input={'tags': unique_tags_list})

    model_text = getattr(response, "content", None) or getattr(response, "text", None) or str(response)

    try:
        json_parser = JsonOutputParser()
        res = json_parser.parse(model_text)
    except OutputParserException as e:
        raise OutputParserException(f"Failed to parse model output as JSON. Model output:\n{model_text}\n\nError: {e}")

    if not isinstance(res, dict):
        raise OutputParserException(f"Expected JSON object mapping; got: {type(res)}")

    return res



def extract_metadata(post):
    template = '''
You are given a LinkedIn post. You need to extract number of lines, language of the post and tags.
1. Return a valid JSON. No preamble.
2. JSON object should have exactly three keys: line_count, language and tags.
3. tags is an array of text tags. Extract maximum two tags.
4. Language should be "English" or "Hinglish" (Hinglish means Hindi + English).

Here is the actual post on which you need to perform this task:
{post}
'''
    pt = PromptTemplate.from_template(template)
    chain = pt | llm
    response = chain.invoke(input={'post': post})

    model_text = getattr(response, "content", None) or getattr(response, "text", None) or str(response)

    try:
        json_parser = JsonOutputParser()
        res = json_parser.parse(model_text)
    except OutputParserException as e:
        raise OutputParserException(f"Failed to parse model output as JSON. Model output:\n{model_text}\n\nError: {e}")
    return res


if __name__ == "__main__":
    process_posts("data/raw_posts.json", "data/processed_posts.json")
