const config = {
  title: 'Emuplane',
  tagline: 'A console and control plane for local AWS emulation',
  favicon: 'img/mark.png',

  url: 'https://mathewmusango.github.io',
  baseUrl: '/emuplane/',
  organizationName: 'mathewmusango',
  projectName: 'emuplane',
  trailingSlash: true,

  onBrokenLinks: 'throw',

  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'throw',
    },
  },
  // Diagram support for the fenced ```mermaid blocks.
  themes: ['@docusaurus/theme-mermaid'],

  // Offline full-text search, built with the site.
  plugins: [
    [
      require.resolve('@easyops-cn/docusaurus-search-local'),
      {
        hashed: true,
        indexBlog: false,
        docsRouteBasePath: '/docs',
        highlightSearchTermsOnTargetPage: true,
      },
    ],
  ],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: require.resolve('./sidebars.js'),
          editUrl: 'https://github.com/mathewmusango/emuplane/tree/main/',
          showLastUpdateTime: false,
        },
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css'),
        },
      },
    ],
  ],

  themeConfig: {
    navbar: {
      title: 'Emuplane',
      logo: {
        alt: 'Emuplane',
        src: 'img/mark.png',
      },
      items: [
        {
          // The working docs, until the next version freeze makes them the default.
          to: '/docs/next/intro',
          position: 'left',
          label: 'Docs',
        },
        {
          type: 'docSidebar',
          sidebarId: 'reference',
          position: 'left',
          label: 'Reference',
        },
        {
          type: 'docSidebar',
          sidebarId: 'api',
          position: 'left',
          label: 'API',
        },
        {
          to: '/changelog',
          label: 'Changelog',
          position: 'left',
        },
        {
          type: 'docsVersionDropdown',
          position: 'right',
        },
        {
          href: 'https://github.com/mathewmusango/emuplane',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            { label: 'Quickstart', to: '/docs/getting-started/quickstart' },
            { label: 'The console', to: '/docs/getting-started/console' },
            { label: 'Architecture', to: '/docs/concepts/architecture' },
            { label: 'S3', to: '/docs/guides/s3' },
          ],
        },
        {
          title: 'Reference',
          items: [
            { label: 'Control API', to: '/docs/reference/control-api' },
            { label: 'S3 coverage', to: '/docs/reference/s3-coverage' },
            { label: 'Configuration', to: '/docs/reference/configuration' },
            { label: 'Limits', to: '/docs/reference/limits' },
          ],
        },
        {
          title: 'Project',
          items: [
            { label: 'GitHub', href: 'https://github.com/mathewmusango/emuplane' },
            {
              label: 'Container image',
              href: 'https://github.com/mathewmusango/emuplane/pkgs/container/emuplane',
            },
            {
              label: 'Releases',
              href: 'https://github.com/mathewmusango/emuplane/releases',
            },
          ],
        },
      ],
      copyright: `Emuplane documentation. Built with Docusaurus.`,
    },
    prism: {
      theme: require('prism-react-renderer').themes.github,
      darkTheme: require('prism-react-renderer').themes.dracula,
      additionalLanguages: ['bash', 'json', 'python', 'yaml', 'rust'],
    },
    // Follow the reader's system theme, with light as the default.
    colorMode: {
      defaultMode: 'light',
      respectPrefersColorScheme: true,
    },
  },
}

module.exports = config
