/** @type {import('@docusaurus/types').DocusaurusConfig} */
module.exports = {
  title: 'ZeroVerify Docs',
  tagline: 'Email verification & decision-maker platform docs',
  url: 'https://<YOUR-GITHUB-USER>.github.io',
  baseUrl: '/<YOUR-REPO-NAME>/',
  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',
  favicon: '/img/favicon.ico',
  organizationName: '<YOUR-GITHUB-USER>',
  projectName: '<YOUR-REPO-NAME>',
  presets: [
    [
      '@docusaurus/preset-classic',
      {
        docs: {
          sidebarPath: require.resolve('./sidebars.js'),
          routeBasePath: '/', // serve docs at root
        },
        theme: {
          customCss: require.resolve('./src/css/custom.css'),
        },
      },
    ],
  ],
};
