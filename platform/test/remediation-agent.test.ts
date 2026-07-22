/**
 * Synth assertions for the Remediation A2A agent stack (M3). Encodes the
 * deployment findings from docs/DESIGN.md "A2A deployment findings" as
 * regression tests.
 */
import * as cdk from 'aws-cdk-lib';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { RemediationAgentStack } from '../lib/remediation-agent-stack';

const ENV = { account: '111111111111', region: 'ap-northeast-1' };
const AGENT_SPACE_ID = 'a0ad2ee6-0000-0000-0000-000000000000';

function synth(context: Record<string, string> = {}) {
  const app = new cdk.App({ context: { projectTag: 'devops-sample-poc', ...context } });
  const stack = new RemediationAgentStack(app, 'TestRemediationAgent', {
    env: ENV,
    agentSpaceId: AGENT_SPACE_ID,
  });
  cdk.Tags.of(app).add('Project', 'devops-sample-poc');
  return Template.fromStack(stack);
}

describe('RemediationAgentStack', () => {
  const t = synth();

  test('creates one A2A AgentCore Runtime with CodeConfiguration (no container)', () => {
    t.resourceCountIs('AWS::BedrockAgentCore::Runtime', 1);
    t.hasResourceProperties('AWS::BedrockAgentCore::Runtime', {
      ProtocolConfiguration: 'A2A',
      NetworkConfiguration: { NetworkMode: 'PUBLIC' },
      AgentRuntimeArtifact: {
        CodeConfiguration: Match.objectLike({
          Runtime: 'PYTHON_3_13',
          EntryPoint: ['agent.py'],
        }),
      },
    });
  });

  test('runtime name matches the AgentRuntimeName pattern (no hyphens)', () => {
    const runtimes = t.findResources('AWS::BedrockAgentCore::Runtime');
    for (const r of Object.values(runtimes)) {
      expect(r.Properties.AgentRuntimeName).toMatch(/^[a-zA-Z][a-zA-Z0-9_]{0,47}$/);
    }
  });

  test('runtime role can invoke ONLY the propose-fix-pr lambda', () => {
    t.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: 'lambda:InvokeFunction',
            Resource: `arn:aws:lambda:${ENV.region}:${ENV.account}:function:gov-blueprint-propose-fix-pr`,
          }),
        ]),
      }),
    });
    // No broader lambda invoke grants anywhere in the stack.
    const policies = t.findResources('AWS::IAM::Policy');
    for (const p of Object.values(policies)) {
      for (const stmt of p.Properties.PolicyDocument.Statement) {
        const actions = Array.isArray(stmt.Action) ? stmt.Action : [stmt.Action];
        if (actions.includes('lambda:InvokeFunction')) {
          const resources = Array.isArray(stmt.Resource) ? stmt.Resource : [stmt.Resource];
          for (const r of resources) {
            if (typeof r === 'string') expect(r).not.toMatch(/function:\*|function:gov-blueprint-\*/);
          }
        }
      }
    }
  });

  test('invoke role trusts aidevops.amazonaws.com with confused-deputy conditions', () => {
    t.hasResourceProperties('AWS::IAM::Role', {
      AssumeRolePolicyDocument: Match.objectLike({
        Statement: Match.arrayWith([
          Match.objectLike({
            Principal: { Service: 'aidevops.amazonaws.com' },
            Condition: Match.objectLike({
              StringEquals: { 'aws:SourceAccount': ENV.account },
              ArnLike: {
                'aws:SourceArn': `arn:aws:aidevops:${ENV.region}:${ENV.account}:service/*`,
              },
            }),
          }),
        ]),
      }),
    });
  });

  test('invoke role grants GetAgentCard (RegisterService validates through this role)', () => {
    const policies = t.findResources('AWS::IAM::Policy');
    const hasCardGrant = Object.values(policies).some((p) =>
      p.Properties.PolicyDocument.Statement.some((stmt: any) => {
        const actions = Array.isArray(stmt.Action) ? stmt.Action : [stmt.Action];
        return (
          actions.includes('bedrock-agentcore:GetAgentCard') &&
          actions.includes('bedrock-agentcore:InvokeAgentRuntime')
        );
      })
    );
    expect(hasCardGrant).toBe(true);
  });

  test('registers + associates via the custom resource by default', () => {
    t.resourceCountIs('Custom::DevOpsAgentRemoteAgent', 1);
    t.hasResourceProperties('Custom::DevOpsAgentRemoteAgent', {
      AgentSpaceId: AGENT_SPACE_ID,
      Name: 'remediation-pr-agent',
      SigningService: 'bedrock-agentcore',
    });
  });

  test('registrar can PassRole only the invoke role', () => {
    const policies = t.findResources('AWS::IAM::Policy');
    for (const p of Object.values(policies)) {
      for (const stmt of p.Properties.PolicyDocument.Statement) {
        const actions = Array.isArray(stmt.Action) ? stmt.Action : [stmt.Action];
        if (actions.includes('iam:PassRole')) {
          expect(stmt.Resource).not.toBe('*');
        }
      }
    }
  });

  test('-c registerRemoteAgent=false deploys the runtime without registration (two-phase bring-up)', () => {
    const t2 = synth({ registerRemoteAgent: 'false' });
    t2.resourceCountIs('AWS::BedrockAgentCore::Runtime', 1);
    expect(Object.keys(t2.findResources('Custom::DevOpsAgentRemoteAgent'))).toHaveLength(0);
  });
});
