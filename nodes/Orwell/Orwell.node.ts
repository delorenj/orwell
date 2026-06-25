import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';

import type { IDataObject, IExecuteFunctions, INodeExecutionData, INodePropertyOptions, INodeType, INodeTypeDescription } from 'n8n-workflow';
import { NodeConnectionTypes, NodeOperationError } from 'n8n-workflow';

const execFileAsync = promisify(execFile);

type OrwellOperation = 'state' | 'in' | 'out';

const operationOptions: INodePropertyOptions[] = [
	{
		name: 'Get State',
		value: 'state',
		description: 'Read the current Orwell clocked-in/out state without changing it',
		action: 'Get Orwell clock state',
	},
	{
		name: 'Clock In',
		value: 'in',
		description: 'Start a work session in Orwell',
		action: 'Clock in via Orwell',
	},
	{
		name: 'Clock Out',
		value: 'out',
		description: 'End a work session in Orwell',
		action: 'Clock out via Orwell',
	},
];

function defaultRepoPath(): string {
	return path.resolve(__dirname, '../../..');
}

function resolvePythonPath(repoPath: string, requestedPythonPath: string): string {
	if (requestedPythonPath.trim() !== '') {
		return requestedPythonPath;
	}

	const repoPython = path.join(repoPath, '.venv', 'bin', 'python');
	if (existsSync(repoPython)) {
		return repoPython;
	}

	return 'python3';
}

function scriptPathForOperation(repoPath: string, operation: OrwellOperation): string {
	const scriptName = operation === 'state' ? '04_clock_state.py' : '03_clock_action.py';
	return path.join(repoPath, 'scripts', scriptName);
}

async function runOrwellOperation(options: {
	operation: OrwellOperation;
	repoPath: string;
	pythonPath: string;
	timeoutMs: number;
}) {
	const scriptPath = scriptPathForOperation(options.repoPath, options.operation);
	if (!existsSync(scriptPath)) {
		throw new Error(`Orwell script not found: ${scriptPath}`);
	}

	const screenshotPath = path.join(
		options.repoPath,
		'outputs',
		options.operation === 'state' ? 'clock_state.png' : `clock_${options.operation}.png`,
	);
	const startedAt = new Date().toISOString();
	const args = options.operation === 'state' ? [scriptPath] : [scriptPath, options.operation];
	const result = await execFileAsync(options.pythonPath, args, {
		cwd: options.repoPath,
		timeout: options.timeoutMs,
		maxBuffer: 1024 * 1024,
		env: process.env,
	});

	const stdout = result.stdout.trim();
	let parsedState: IDataObject | null = null;
	if (options.operation === 'state' && stdout !== '') {
		parsedState = JSON.parse(stdout) as IDataObject;
	}

	return {
		operation: options.operation,
		repoPath: options.repoPath,
		pythonPath: options.pythonPath,
		scriptPath,
		screenshotPath,
		startedAt,
		finishedAt: new Date().toISOString(),
		stdout,
		stderr: result.stderr.trim(),
		state: parsedState,
		success: true,
	};
}

export class Orwell implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'Orwell',
		name: 'orwell',
		icon: 'file:orwell.svg',
		group: ['transform'],
		version: 1,
		subtitle: '={{$parameter["operation"] === "state" ? "Get State" : $parameter["operation"] === "in" ? "Clock In" : "Clock Out"}}',
		description: 'Read Orwell clock state and trigger clock-in/clock-out automation from n8n',
		defaults: {
			name: 'Orwell',
		},
		inputs: [NodeConnectionTypes.Main],
		outputs: [NodeConnectionTypes.Main],
		usableAsTool: true,
		properties: [
			{
				displayName: 'Operation',
				name: 'operation',
				type: 'options',
				options: operationOptions,
				default: 'state',
				noDataExpression: true,
				required: true,
			},
			{
				displayName: 'Repository Path',
				name: 'repoPath',
				type: 'string',
				default: defaultRepoPath(),
				required: true,
				description: 'Absolute path to the Orwell repo containing scripts/03_clock_action.py and scripts/04_clock_state.py',
			},
			{
				displayName: 'Python Path',
				name: 'pythonPath',
				type: 'string',
				default: '',
				description: 'Optional Python executable path. Leave blank to use <repo>/.venv/bin/python, then python3',
			},
			{
				displayName: 'Timeout Seconds',
				name: 'timeoutSeconds',
				type: 'number',
				default: 600,
				typeOptions: {
					minValue: 1,
				},
				description: 'Maximum time to wait for the Orwell browser automation to finish',
			},
		],
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const returnData: INodeExecutionData[] = [];

		for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
			try {
				const operation = this.getNodeParameter('operation', itemIndex) as OrwellOperation;
				const repoPath = this.getNodeParameter('repoPath', itemIndex) as string;
				const pythonPath = resolvePythonPath(
					repoPath,
					this.getNodeParameter('pythonPath', itemIndex, '') as string,
				);
				const timeoutSeconds = this.getNodeParameter('timeoutSeconds', itemIndex) as number;

				const result = await runOrwellOperation({
					operation,
					repoPath,
					pythonPath,
					timeoutMs: timeoutSeconds * 1000,
				});

				returnData.push({ json: result, pairedItem: itemIndex });
			} catch (error) {
				if (this.continueOnFail()) {
					returnData.push({
						json: {
							success: false,
							error: error instanceof Error ? error.message : String(error),
						},
						pairedItem: itemIndex,
					});
					continue;
				}

				throw new NodeOperationError(this.getNode(), error as Error, { itemIndex });
			}
		}

		return [returnData];
	}
}
