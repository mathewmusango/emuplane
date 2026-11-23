// The IAM console is its own section: dashboard, identities, policies and reports over the emulator's API.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import IAMSection from '../../web/src/pages/IAMSection'
import { META, installFetch, renderAt } from './fixtures'

const trust = encodeURIComponent(
  JSON.stringify({
    Version: '2012-10-17',
    Statement: [
      {
        Effect: 'Allow',
        Principal: { Service: 'lambda.amazonaws.com' },
        Action: 'sts:AssumeRole',
      },
    ],
  }),
)

const XML = {
  'get-account-summary': `<GetAccountSummaryResponse><GetAccountSummaryResult><SummaryMap>
    <entry><key>AccountMFAEnabled</key><value>1</value></entry>
    <entry><key>AccountAccessKeysPresent</key><value>0</value></entry>
  </SummaryMap></GetAccountSummaryResult></GetAccountSummaryResponse>`,
  'list-account-aliases': `<ListAccountAliasesResponse><ListAccountAliasesResult>
    <AccountAliases><member>platform-team</member></AccountAliases>
  </ListAccountAliasesResult></ListAccountAliasesResponse>`,
  'list-users': `<ListUsersResponse><ListUsersResult><Users>
    <member><UserName>mpeter</UserName><Path>/</Path><CreateDate>2026-01-01T00:00:00Z</CreateDate></member>
    <member><UserName>readonly</UserName><Path>/team/</Path><CreateDate>2026-02-01T00:00:00Z</CreateDate></member>
  </Users></ListUsersResult></ListUsersResponse>`,
  'list-groups-for-user': '<ListGroupsForUserResponse><ListGroupsForUserResult><Groups></Groups></ListGroupsForUserResult></ListGroupsForUserResponse>',
  'list-mfa-devices': '<ListMFADevicesResponse><ListMFADevicesResult><MFADevices></MFADevices></ListMFADevicesResult></ListMFADevicesResponse>',
  'create-user': '<CreateUserResponse/>',
  'create-virtual-mfa-device': `<CreateVirtualMFADeviceResponse><CreateVirtualMFADeviceResult>
    <VirtualMFADevice><SerialNumber>arn:aws:iam::111111111111:mfa/mpeter-mfa</SerialNumber>
    <Base32StringSeed>${btoa('JBSWY3DPEHPK3PXP')}</Base32StringSeed></VirtualMFADevice>
  </CreateVirtualMFADeviceResult></CreateVirtualMFADeviceResponse>`,
  'enable-mfa-device': '<EnableMFADeviceResponse/>',
  'create-account-alias': '<CreateAccountAliasResponse/>',
  'delete-account-alias': '<DeleteAccountAliasResponse/>',
  'list-access-keys': '<ListAccessKeysResponse><ListAccessKeysResult><AccessKeyMetadata></AccessKeyMetadata></ListAccessKeysResult></ListAccessKeysResponse>',
  'list-attached-user-policies': '<ListAttachedUserPoliciesResponse><ListAttachedUserPoliciesResult><AttachedPolicies></AttachedPolicies></ListAttachedUserPoliciesResult></ListAttachedUserPoliciesResponse>',
  'list-user-policies': '<ListUserPoliciesResponse><ListUserPoliciesResult><PolicyNames></PolicyNames></ListUserPoliciesResult></ListUserPoliciesResponse>',
  'list-groups': `<ListGroupsResponse><ListGroupsResult><Groups>
    <member><GroupName>platform</GroupName><Path>/</Path><CreateDate>2026-01-02T00:00:00Z</CreateDate></member>
  </Groups></ListGroupsResult></ListGroupsResponse>`,
  'get-group': '<GetGroupResponse><GetGroupResult><Group><GroupName>platform</GroupName></Group><Users></Users></GetGroupResult></GetGroupResponse>',
  'list-attached-group-policies': '<ListAttachedGroupPoliciesResponse><ListAttachedGroupPoliciesResult><AttachedPolicies></AttachedPolicies></ListAttachedGroupPoliciesResult></ListAttachedGroupPoliciesResponse>',
  'list-group-policies': '<ListGroupPoliciesResponse><ListGroupPoliciesResult><PolicyNames></PolicyNames></ListGroupPoliciesResult></ListGroupPoliciesResponse>',
  'list-roles': `<ListRolesResponse><ListRolesResult><Roles>
    <member><RoleName>metrics-reader</RoleName><Path>/</Path><CreateDate>2026-01-03T00:00:00Z</CreateDate><MaxSessionDuration>3600</MaxSessionDuration><AssumeRolePolicyDocument>${trust}</AssumeRolePolicyDocument></member>
  </Roles></ListRolesResult></ListRolesResponse>`,
  'list-policies': `<ListPoliciesResponse><ListPoliciesResult><Policies>
    <member><PolicyName>read-logs</PolicyName><Arn>arn:aws:iam::111111111111:policy/read-logs</Arn><AttachmentCount>1</AttachmentCount><Description>Reads logs</Description></member>
    <member><PolicyName>AdministratorAccess</PolicyName><Arn>arn:aws:iam::aws:policy/AdministratorAccess</Arn><AttachmentCount>0</AttachmentCount></member>
  </Policies></ListPoliciesResult></ListPoliciesResponse>`,
  'list-open-id-connect-providers': `<ListOpenIDConnectProvidersResponse><ListOpenIDConnectProvidersResult>
    <OpenIDConnectProviderList><member><Arn>arn:aws:iam::111111111111:oidc-provider/oidc.example.com</Arn></member></OpenIDConnectProviderList>
  </ListOpenIDConnectProvidersResult></ListOpenIDConnectProvidersResponse>`,
  'get-open-id-connect-provider': '<GetOpenIDConnectProviderResponse><GetOpenIDConnectProviderResult><CreateDate>2026-01-04T00:00:00Z</CreateDate></GetOpenIDConnectProviderResult></GetOpenIDConnectProviderResponse>',
  'list-saml-providers': '<ListSAMLProvidersResponse><ListSAMLProvidersResult><SAMLProviderList></SAMLProviderList></ListSAMLProvidersResult></ListSAMLProvidersResponse>',
  'get-account-password-policy': '<GetAccountPasswordPolicyResponse><GetAccountPasswordPolicyResult><PasswordPolicy><MinimumPasswordLength>14</MinimumPasswordLength><RequireSymbols>true</RequireSymbols><RequireNumbers>true</RequireNumbers><RequireUppercaseCharacters>true</RequireUppercaseCharacters><RequireLowercaseCharacters>true</RequireLowercaseCharacters><AllowUsersToChangePassword>true</AllowUsersToChangePassword></PasswordPolicy></GetAccountPasswordPolicyResult></GetAccountPasswordPolicyResponse>',
  'generate-credential-report': '<GenerateCredentialReportResponse><GenerateCredentialReportResult><State>COMPLETE</State></GenerateCredentialReportResult></GenerateCredentialReportResponse>',
  'get-credential-report': `<GetCredentialReportResponse><GetCredentialReportResult>
    <Content>${btoa('user,arn\n<root_account>,arn:aws:iam::111111111111:root\n')}</Content>
    <GeneratedTime>2026-11-22T12:00:00Z</GeneratedTime>
  </GetCredentialReportResult></GetCredentialReportResponse>`,
}

const execBodies = []

const exec = (_url, init) => {
  const body = JSON.parse(init.body)
  execBodies.push(body)
  return { ok: true, status: 200, body: XML[body.operation] || '<Empty/>' }
}

const USER_ROUTES = {
  '/api/mfa': { enabled: false, serial: '', devices: [] },
  '/api/mfa/device': {
    ok: true,
    serial: 'arn:aws:iam::111111111111:mfa/mpeter-mfa',
    seed: 'JBSWY3DPEHPK3PXP',
  },
  '/api/mfa/enrol': { ok: true, serial: 'arn:aws:iam::111111111111:mfa/mpeter-mfa' },
  '/api/users': [
    {
      account_id: '111111111111',
      alias: 'mathewmusango',
      name: 'Mathew Musango',
      regions: ['us-east-1'],
      global_admin: false,
      users: [
        { username: 'root', role: 'root' },
        { username: 'mpeter', role: 'iam' },
      ],
    },
  ],
  '/api/users/mpeter': { deleted: 'mpeter', account: '111111111111' },
  '/api/users/mpeter/password': {
    user: 'mpeter',
    account: '111111111111',
    sessions_revoked: true,
  },
}

beforeEach(() => {
  execBodies.length = 0
  installFetch({ ...USER_ROUTES, '/api/exec': exec })
})

describe('IAM dashboard', () => {
  it('reads the account summary, the counts and the alias as the root', async () => {
    renderAt(<IAMSection section="dashboard" />, ['/iam/dashboard'])

    expect(await screen.findByRole('heading', { name: 'IAM Dashboard', level: 1 })).toBeTruthy()
    expect(await screen.findByText('platform-team')).toBeTruthy()
    expect(screen.getAllByText('111111111111').length).toBeGreaterThan(0)
    expect(screen.getByText('https://emuplane.example.com/login?account=platform-team')).toBeTruthy()
    expect(screen.getByText('Root user has MFA')).toBeTruthy()
    expect(screen.getByText('Root user has no active access keys')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Add MFA' })).toBeNull()
  })

  it('offers Add MFA to an IAM user and enrols the device', async () => {
    installFetch({
      ...USER_ROUTES,
      '/api/exec': exec,
      '/api/meta': { ...META, me: { ...META.me, user: 'mpeter', role: 'iam' } },
    })
    renderAt(<IAMSection section="dashboard" />, ['/iam/dashboard'])

    expect(await screen.findByText('Root user has MFA')).toBeTruthy()
    expect(await screen.findByText('Add MFA for yourself')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Add MFA' }))

    expect(
      (await screen.findAllByText('arn:aws:iam::111111111111:mfa/mpeter-mfa')).length,
    ).toBeGreaterThan(0)
    const qr = screen.getByAltText('QR code for the virtual MFA device')
    expect(qr.getAttribute('src')).toMatch(/^data:image\//)
    fireEvent.change(screen.getByLabelText('Code'), { target: { value: '123456' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'Add device' }).at(-1))

    await waitFor(() => {
      const call = global.fetch.mock.calls.find(
        ([url, init]) => String(url) === '/api/mfa/enrol' && init.method === 'POST',
      )
      expect(call).toBeTruthy()
      expect(JSON.parse(call[1].body)).toMatchObject({
        serial: 'arn:aws:iam::111111111111:mfa/mpeter-mfa',
        seed: 'JBSWY3DPEHPK3PXP',
        code: '123456',
      })
    })
  })

  it('removes MFA from the IAM user', async () => {
    installFetch({
      ...USER_ROUTES,
      '/api/exec': exec,
      '/api/meta': { ...META, me: { ...META.me, user: 'mpeter', role: 'iam' } },
      '/api/mfa': {
        enabled: true,
        serial: 'arn:aws:iam::111111111111:mfa/mpeter-mfa',
        devices: [
          {
            serial: 'arn:aws:iam::111111111111:mfa/mpeter-mfa',
            user: 'mpeter',
            enabled: true,
          },
        ],
      },
    })
    renderAt(<IAMSection section="dashboard" />, ['/iam/dashboard'])

    expect(await screen.findByText('MFA is enabled for your user')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Remove MFA' }))

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(
          ([url, init]) => String(url) === '/api/mfa' && init.method === 'DELETE',
        ),
      ).toBe(true)
    })
  })

  it('edits and deletes the account alias', async () => {
    renderAt(<IAMSection section="dashboard" />, ['/iam/dashboard'])

    await screen.findByText('platform-team')
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('Alias'), {
      target: { value: 'platform-team-new' },
    })
    fireEvent.click(screen.getAllByRole('button', { name: 'Save' }).at(-1))
    await waitFor(() => {
      expect(
        execBodies.some(
          (body) =>
            body.operation === 'create-account-alias' &&
            body.params.AccountAlias === 'platform-team-new',
        ),
      ).toBe(true)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => {
      expect(execBodies.some((body) => body.operation === 'delete-account-alias')).toBe(
        true,
      )
    })
  })

  it('shows the IAM navigation on the service sidebar', async () => {
    renderAt(<IAMSection section="dashboard" />, ['/iam/dashboard'])

    expect(await screen.findByRole('link', { name: 'IAM users' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Roles' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Credential report' })).toBeTruthy()
    expect(screen.getByText('Identity and Access Management (IAM)')).toBeTruthy()
  })
})

describe('IAM users', () => {
  it('lists the emulator users, then creates one through the control route', async () => {
    renderAt(<IAMSection section="users" />, ['/iam/users'])

    expect(await screen.findByText('mpeter')).toBeTruthy()
    expect(screen.getByText('readonly')).toBeTruthy()

    fireEvent.click(screen.getAllByRole('button', { name: 'Create user' })[0])
    fireEvent.change(screen.getByLabelText('User name'), {
      target: { value: 'deploy-bot' },
    })
    fireEvent.change(screen.getByLabelText('Console password'), {
      target: { value: 'long-enough-password' },
    })
    fireEvent.click(screen.getAllByRole('button', { name: 'Create user' }).at(-1))

    await waitFor(() => {
      const call = global.fetch.mock.calls.find(
        ([url, init]) => String(url) === '/api/users' && init.method === 'POST',
      )
      expect(call).toBeTruthy()
      expect(JSON.parse(call[1].body)).toMatchObject({
        username: 'deploy-bot',
        password: 'long-enough-password',
      })
    })
  })

  it('deletes a selected user after confirming, and sets a console password', async () => {
    renderAt(<IAMSection section="users" />, ['/iam/users'])

    await screen.findByText('mpeter')
    fireEvent.click(screen.getAllByRole('radio')[0])
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete user' })[0])
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete user' }).at(-1))

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(
          ([url, init]) =>
            String(url).startsWith('/api/users/mpeter?') && init.method === 'DELETE',
        ),
      ).toBe(true)
    })

    fireEvent.click(screen.getAllByRole('radio')[0])
    fireEvent.click(screen.getAllByRole('button', { name: 'Set password' })[0])
    fireEvent.change(screen.getByLabelText(/New password for/), {
      target: { value: 'another-long-password' },
    })
    fireEvent.click(screen.getAllByRole('button', { name: 'Set password' }).at(-1))

    await waitFor(() => {
      expect(
        global.fetch.mock.calls.some(
          ([url, init]) =>
            String(url) === '/api/users/mpeter/password' && init.method === 'POST',
        ),
      ).toBe(true)
    })
  })
})

describe('IAM entities', () => {
  it('lists groups, roles and policies with the fields the console shows', async () => {
    const groups = renderAt(<IAMSection section="groups" />, ['/iam/groups'])
    expect(await screen.findByText('platform')).toBeTruthy()
    groups.unmount()

    const roles = renderAt(<IAMSection section="roles" />, ['/iam/roles'])
    expect(await screen.findByText('metrics-reader')).toBeTruthy()
    expect(screen.getByText('AWS service: lambda.amazonaws.com')).toBeTruthy()
    roles.unmount()

    renderAt(<IAMSection section="policies" />, ['/iam/policies'])
    expect(await screen.findByText('read-logs')).toBeTruthy()
    expect(screen.getByText('Customer managed')).toBeTruthy()
    expect(screen.getByText('AWS managed')).toBeTruthy()
  })

  it('lists identity providers by type', async () => {
    renderAt(<IAMSection section="providers" />, ['/iam/providers'])

    expect(await screen.findByText('oidc.example.com')).toBeTruthy()
    expect(screen.getAllByText('OpenID Connect').length).toBeGreaterThan(0)
  })

  it('reads the password policy and the account alias', async () => {
    renderAt(<IAMSection section="settings" />, ['/iam/settings'])

    expect(await screen.findByText('14 characters')).toBeTruthy()
    expect(screen.getByText('platform-team')).toBeTruthy()
  })

  it('generates and downloads the credential report', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:report')
    URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    renderAt(<IAMSection section="report" />, ['/iam/report'])
    fireEvent.click(await screen.findByRole('button', { name: 'Generate and download report' }))

    await waitFor(() => {
      expect(execBodies.map((body) => body.operation)).toEqual(
        expect.arrayContaining(['generate-credential-report', 'get-credential-report']),
      )
    })
    expect(await screen.findByText('Generated 2026-11-22T12:00:00Z.')).toBeTruthy()
  })
})
