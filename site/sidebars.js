// One sidebar per navbar tab. A doc belongs to exactly one of them, so no page is
// reachable twice and each tab's sidebar is the whole of that area.
module.exports = {
  // The tutorial: read this first, then the pages behind each idea.
  docs: [
    'intro',
    {
      type: 'category',
      label: 'Getting started',
      collapsed: false,
      items: [
        {type: 'doc', id: 'getting-started/index', label: 'Overview'},
        'getting-started/quickstart',
        'getting-started/access',
        'getting-started/console',
        'getting-started/access-keys',
      ],
    },
    {
      type: 'category',
      label: 'Deployment',
      collapsed: false,
      items: [
        {type: 'doc', id: 'deployment/index', label: 'Overview'},
        'deployment/docker',
        'deployment/podman',
        'deployment/upgrading',
      ],
    },
    {
      type: 'category',
      label: 'Concepts',
      collapsed: false,
      items: [
        {type: 'doc', id: 'concepts/index', label: 'Overview'},
        'concepts/architecture',
        'concepts/tenancy',
        'concepts/extensions',
      ],
    },
    {
      type: 'category',
      label: 'Guides',
      collapsed: false,
      items: [
        {type: 'doc', id: 'guides/index', label: 'Overview'},
        'guides/s3',
        'guides/troubleshooting',
      ],
    },
    {
      // The operator side: how the thing is run, released and versioned.
      type: 'category',
      label: 'Operations',
      collapsed: false,
      items: [
        {type: 'doc', id: 'operations/index', label: 'Overview'},
        'operations/runbook',
        'operations/releases',
        'operations/image-and-versions',
      ],
    },
  ],

  // What the console can do, operation by operation, and what it cannot. The
  // coverage map's group pages are the only per-service navigation; no sidebar
  // grows a line per service, because that list is the group page's table.
  reference: [
    'reference/index',
    {
      type: 'category',
      label: 'Coverage',
      collapsed: false,
      items: [
        {type: 'doc', id: 'coverage/index', label: 'Overview'},
        'coverage/core/index',
        'coverage/extended/index',
        'coverage/infrastructure/index',
        'coverage/cloudformation/index',
      ],
    },
    'reference/configuration',
    'reference/limits',
  ],

  // The control API is generated from the control's own route table, so it is its own tab.
  api: ['reference/control-api'],
}
