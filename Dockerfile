# Use the official AWS Lambda Python base image
FROM public.ecr.aws/lambda/python:3.11

# Copy requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install dependencies
# Using psycopg2-binary; AL2 / AL2023 compatible version is needed. 
# The Lambda python base image handles this correctly for Amazon Linux.
RUN pip install -r requirements.txt

# Copy all project files
COPY . ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD [ "handler.handler" ]
