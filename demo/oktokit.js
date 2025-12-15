const { Octokit } = require('@octokit/rest');
const { throttling } = require('@octokit/plugin-throttling');
const { retry } = require('@octokit/plugin-retry');
const { paginate } = require('@octokit/plugin-paginate-rest');

/**
 * EXAMPLE 1: Practical Usage - Get User Info
 * Most basic and common use case
 */
async function exampleGetUserInfo() {
  const octokit = new Octokit({
    auth: process.env.GITHUB_TOKEN,
  });

  try {
    const { data: user } = await octokit.rest.users.getAuthenticated();
    console.log(`Authenticated as: ${user.login}`);
    console.log(`Name: ${user.name}`);
    console.log(`Bio: ${user.bio}`);
    console.log(`Public repos: ${user.public_repos}`);
  } catch (error) {
    console.error('Error fetching user info:', error);
  }
}

/**
 * EXAMPLE 2: Pagination Plugin
 * Essential for fetching large datasets - automatically handles all pages
 */
async function examplePagination() {
  const MyOctokit = Octokit.plugin(paginate);

  const octokit = new MyOctokit({
    auth: process.env.GITHUB_TOKEN,
  });

  try {
    // Fetch all issues (automatically handles pagination)
    const allIssues = await octokit.paginate(
      'GET /repos/{owner}/{repo}/issues',
      {
        owner: 'github',
        repo: 'docs',
      }
    );

    console.log(`Total issues: ${allIssues.length}`);
    allIssues.forEach((issue) => {
      console.log(`- ${issue.number}: ${issue.title}`);
    });
  } catch (error) {
    console.error('Error fetching issues:', error);
  }
}

/**
 * EXAMPLE 3: Practical Usage - List Pull Requests
 * Common workflow - list and filter PRs with pagination
 */
async function exampleListPullRequests() {
  const MyOctokit = Octokit.plugin(paginate);

  const octokit = new MyOctokit({
    auth: process.env.GITHUB_TOKEN,
  });

  try {
    const pullRequests = await octokit.paginate(
      'GET /repos/{owner}/{repo}/pulls',
      {
        owner: 'github',
        repo: 'docs',
        state: 'open',
        per_page: 100,
      }
    );

    console.log(`Found ${pullRequests.length} open pull requests`);
    pullRequests.slice(0, 5).forEach((pr) => {
      console.log(`- PR #${pr.number}: ${pr.title} (by ${pr.user.login})`);
    });
  } catch (error) {
    console.error('Error fetching pull requests:', error);
  }
}

/**
 * EXAMPLE 4: Practical Usage - Create an Issue
 * Common automation task
 */
async function exampleCreateIssue() {
  const octokit = new Octokit({
    auth: process.env.GITHUB_TOKEN,
  });

  try {
    const { data: issue } = await octokit.rest.issues.create({
      owner: 'your-username',
      repo: 'your-repo',
      title: 'Test Issue',
      body: 'This is a test issue created with Octokit',
      labels: ['bug', 'enhancement'],
    });

    console.log(`Created issue #${issue.number}: ${issue.title}`);
    console.log(`URL: ${issue.html_url}`);
  } catch (error) {
    console.error('Error creating issue:', error);
  }
}

/**
 * EXAMPLE 5: Multiple Plugins Combined
 * Best practice for production - combines throttling and retry for reliability
 */
function exampleMultiplePlugins() {
  const MyOctokit = Octokit.plugin(throttling, retry);

  const octokit = new MyOctokit({
    auth: process.env.GITHUB_TOKEN,
    throttle: {
      onRateLimit: (retryAfter, options) => {
        console.log(
          `RateLimit hit on ${options.method} ${options.url}. Retrying after ${retryAfter}s`
        );
        return true;
      },
      onAbuseLimit: (retryAfter, options) => {
        console.log(`Abuse limit hit on ${options.method} ${options.url}`);
      },
    },
    request: {
      retries: 3,
    },
  });

  return octokit;
}

/**
 * EXAMPLE 6: Octokit with Retry Plugin
 * Automatically retries failed requests
 */
function exampleRetry() {
  const MyOctokit = Octokit.plugin(retry);

  const octokit = new MyOctokit({
    auth: process.env.GITHUB_TOKEN,
    request: {
      retries: 3,
      retryAfter: 1,
    },
  });

  return octokit;
}

/**
 * EXAMPLE 7: Basic Octokit with Throttling Plugin
 * Handles API rate limiting automatically
 */
function exampleThrottling() {
  const MyOctokit = Octokit.plugin(throttling);

  const octokit = new MyOctokit({
    auth: process.env.GITHUB_TOKEN,
    throttle: {
      onRateLimit: (retryAfter, options, octokit, retryCount) => {
        octokit.log.warn(
          `Request quota exhausted for request ${options.method} ${options.url}`
        );

        // Retry once after hitting rate limit
        if (retryCount < 1) {
          octokit.log.info(`Retrying after ${retryAfter} seconds!`);
          return true;
        }
      },
      onAbuseLimit: (retryAfter, options, octokit) => {
        // Does not retry, only logs a warning
        octokit.log.warn(
          `Abuse detected for request ${options.method} ${options.url}`
        );
      },
    },
  });

  return octokit;
}

/**
 * EXAMPLE 8: Custom Plugin
 * Create and use a custom plugin for logging and request interception
 */
const customPlugin = (octokit) => {
  octokit.log.info('Custom plugin initialized');

  octokit.hook.wrap('request', async (request, options) => {
    console.log(`Making request to ${options.method} ${options.url}`);
    const response = await request(options);
    console.log(`Response status: ${response.status}`);
    return response;
  });
};

function exampleCustomPlugin() {
  const MyOctokit = Octokit.plugin(customPlugin);

  const octokit = new MyOctokit({
    auth: process.env.GITHUB_TOKEN,
  });

  return octokit;
}

// Export functions for use in other modules
module.exports = {
  exampleThrottling,
  exampleRetry,
  exampleMultiplePlugins,
  examplePagination,
  exampleCustomPlugin,
  exampleGetUserInfo,
  exampleCreateIssue,
  exampleListPullRequests,
};

// Run examples (uncomment to test)
// exampleGetUserInfo();
// exampleListPullRequests();
