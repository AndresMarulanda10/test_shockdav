from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct
import os
import json


class BitgetStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Results bucket for per-symbol and aggregated JSON files
        results_bucket = s3.Bucket(
            self,
            "BitgetResultsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=False,
        )

        # Secrets Manager secret for Bitget credentials (placeholder)
        credentials_secret = secretsmanager.Secret(
            self,
            "BitgetCredentials",
            secret_name="bitget/credentials",
            description="Bitget API credentials used by Lambdas",
        )

        # IAM role for Coordinator Lambda
        coordinator_role = iam.Role(
            self,
            "CoordinatorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for coordinator Lambda to start Step Function executions",
        )
        coordinator_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"))
        # Allow X-Ray write (if tracing enabled)
        coordinator_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AWSXRayDaemonWriteAccess"))

        # IAM role for Worker Lambda
        worker_role = iam.Role(
            self,
            "WorkerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for worker Lambdas to call Bitget and write to S3",
        )
        worker_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"))
        # Allow X-Ray write for tracing
        worker_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AWSXRayDaemonWriteAccess"))
        # allow PutObject to the results bucket
        results_bucket.grant_put(worker_role)
        # allow reading the secret
        credentials_secret.grant_read(worker_role)

        # IAM role for Collector / Aggregator Lambda
        collector_role = iam.Role(
            self,
            "CollectorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for collector Lambda to aggregate results and write final JSON to S3",
        )
        collector_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"))
        # Allow X-Ray write for tracing
        collector_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AWSXRayDaemonWriteAccess"))
        results_bucket.grant_read_write(collector_role)
        credentials_secret.grant_read(collector_role)

        # Common lambda properties
        lambda_timeout = Duration.seconds(60)
        lambda_runtime = _lambda.Runtime.PYTHON_3_11

        # Coordinator Lambda - responsible for starting Step Function execution
        coordinator_lambda = _lambda.Function(
            self,
            "CoordinatorLambda",
            runtime=lambda_runtime,
            handler="handler.handler",
            code=_lambda.Code.from_asset(os.path.join(os.getcwd(), "src/lambdas/coordinator")),
            timeout=lambda_timeout,
            role=coordinator_role,
            environment={
                "STATE_MACHINE_ARN": "",  # filled after state machine creation
                "CREDENTIALS_SECRET_NAME": credentials_secret.secret_name,
                "AWS_REGION": self.region,
            },
        )

        # Worker Lambda - called for each symbol (Map state)
        worker_lambda = _lambda.Function(
            self,
            "WorkerLambda",
            runtime=lambda_runtime,
            handler="app.handler",
            code=_lambda.Code.from_asset(os.path.join(os.getcwd(), "src/lambdas/worker")),
            timeout=Duration.seconds(120),
            memory_size=512,
            role=worker_role,
            environment={
                "RESULTS_BUCKET": results_bucket.bucket_name,
                "CREDENTIALS_SECRET_NAME": credentials_secret.secret_name,
                "AWS_REGION": self.region,
            },
        )

        # Collector Lambda - aggregates map results and writes final file
        collector_lambda = _lambda.Function(
            self,
            "CollectorLambda",
            runtime=lambda_runtime,
            handler="handler.handler",
            code=_lambda.Code.from_asset(os.path.join(os.getcwd(), "src/lambdas/aggregator")),
            timeout=Duration.seconds(300),
            memory_size=1024,
            role=collector_role,
            environment={
                "RESULTS_BUCKET": results_bucket.bucket_name,
                "RESULTS_PREFIX": "bitget-orders/",
                "AWS_REGION": self.region,
            },
        )

        # Grant invocation permissions from Step Functions (LambdaInvoke will handle this on tasks)
        # Build the Step Functions state machine from a canonical ASL JSON file
        asl_path = os.path.join(os.getcwd(), "step_functions", "init.json")
        asl_json = None
        if os.path.exists(asl_path):
            with open(asl_path, "r", encoding="utf-8") as f:
                asl_json = json.load(f)

            # Replace known placeholder Lambda resource ARNs in the ASL with the Lambdas created in this stack
            def replace_resources(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == "Resource" and isinstance(v, str):
                            # Substitute common placeholder function names with actual function ARNs
                            if v.endswith(":bitget-worker") or v.endswith(":bitget-worker"):
                                obj[k] = worker_lambda.function_arn
                            elif v.endswith(":bitget-aggregator") or v.endswith(":bitget-collector"):
                                obj[k] = collector_lambda.function_arn
                            elif ":bitget-worker" in v:
                                obj[k] = worker_lambda.function_arn
                            elif ":bitget-aggregator" in v or ":bitget-collector" in v:
                                obj[k] = collector_lambda.function_arn
                            # otherwise leave external ARNs intact
                        else:
                            replace_resources(v)
                elif isinstance(obj, list):
                    for item in obj:
                        replace_resources(item)

            replace_resources(asl_json)

            # Collect referenced lambda ARNs from the ASL so we can grant invoke permissions
            referenced_arns = set()

            def collect_resources(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == "Resource" and isinstance(v, str) and v.startswith("arn:aws:lambda"):
                            referenced_arns.add(v)
                        else:
                            collect_resources(v)
                elif isinstance(obj, list):
                    for item in obj:
                        collect_resources(item)

            collect_resources(asl_json)

        # Create a role for Step Functions with least-privilege to invoke the referenced Lambdas
        sf_role = iam.Role(
            self,
            "StepFunctionsRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            description="Role assumed by Step Functions to invoke Lambdas",
        )

        # Allow invocation of Lambdas referenced in the ASL and the ones we created here
        lambda_invoke_resources = list(referenced_arns) + [worker_lambda.function_arn, collector_lambda.function_arn]
        if lambda_invoke_resources:
            sf_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["lambda:InvokeFunction"],
                    resources=list(set(lambda_invoke_resources)),
                )
            )

        # Also grant Step Functions role permission to log to CloudWatch (basic)
        sf_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"))

        # If we loaded an ASL, create a low-level CfnStateMachine using the definition string
        from aws_cdk import CfnOutput

        if asl_json is not None:
            state_machine = sfn.CfnStateMachine(
                self,
                "BitgetStateMachine",
                role_arn=sf_role.role_arn,
                definition_string=json.dumps(asl_json),
            )

            # Update coordinator lambda environment with the state machine ARN
            coordinator_lambda.add_environment("STATE_MACHINE_ARN", state_machine.attr_arn)

            # Restrict coordinator role to only be able to start the created state machine
            coordinator_role.add_to_policy(
                iam.PolicyStatement(actions=["states:StartExecution"], resources=[state_machine.attr_arn])
            )

            # Allow Step Functions to invoke collector and worker lambdas (best-effort)
            worker_lambda.grant_invoke(iam.ServicePrincipal("states.amazonaws.com"))
            collector_lambda.grant_invoke(iam.ServicePrincipal("states.amazonaws.com"))

            # Output bucket name and state machine ARN via stack outputs
            CfnOutput(self, "ResultsBucketName", value=results_bucket.bucket_name)
            CfnOutput(self, "StateMachineArn", value=state_machine.attr_arn)
        else:
            # Fallback: create a simple programmatic state machine (previous behavior)
            worker_invoke = tasks.LambdaInvoke(
                self,
                "InvokeWorker",
                lambda_function=worker_lambda,
                payload_response_only=True,
            )
            map_state = sfn.Map(
                self,
                "MapSymbols",
                max_concurrency=8,
                items_path="$.symbols",
                result_path="$.mapResults",
            )
            map_state.iterator(worker_invoke)
            collector_task = tasks.LambdaInvoke(
                self,
                "RunCollector",
                lambda_function=collector_lambda,
                payload=sfn.TaskInput.from_object({"results": sfn.JsonPath.string_at("$.mapResults"), "startTimeMs": sfn.JsonPath.string_at("$.startTimeMs")}),
                payload_response_only=True,
            )
            definition = map_state.next(collector_task)
            state_machine = sfn.StateMachine(
                self,
                "BitgetStateMachineProgrammatic",
                definition=definition,
                state_machine_type=sfn.StateMachineType.STANDARD,
            )
            coordinator_lambda.add_environment("STATE_MACHINE_ARN", state_machine.state_machine_arn)

            coordinator_role.add_to_policy(
                iam.PolicyStatement(actions=["states:StartExecution"], resources=[state_machine.state_machine_arn])
            )

            worker_lambda.grant_invoke(iam.ServicePrincipal("states.amazonaws.com"))
            collector_lambda.grant_invoke(iam.ServicePrincipal("states.amazonaws.com"))

            CfnOutput(self, "ResultsBucketName", value=results_bucket.bucket_name)
            CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)

