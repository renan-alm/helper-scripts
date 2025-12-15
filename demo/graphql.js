const { graphql } = require('@octokit/graphql');

// ✅ Examples 1-4: Basic queries, variables, aliases, fragments (all GitHub-specific)
// ✅ Example 5: Union Types - Now shows Repository/User union members with proper fields
// ✅ Example 6: Interfaces - Issue/PullRequest with real GitHub fields
// ✅ Example 7: Directives - Using @include/@skip with GitHub viewer fields (company, bio)
// ✅ Example 8: Pagination - Cursor-based GitHub repo pagination
// ✅ Example 9: Nested Queries - GitHub repo with owner and commit history
// ✅ Example 10: Mutation - Shows actual GitHub addComment mutation syntax with proper variables


// Initialize GraphQL client with GitHub token
const graphqlWithAuth = graphql.defaults({
  headers: {
    authorization: `token ${process.env.GITHUB_TOKEN}`,
  },
});

/**
 * EXAMPLE 1: Basic Query - Simple Field Selection
 * Demonstrates basic query structure and field selection
 */
async function exampleBasicQuery() {
  const query = `
    query {
      viewer {
        login
        name
        bio
        followers {
          totalCount
        }
        repositories(first: 5) {
          totalCount
          edges {
            node {
              name
              description
            }
          }
        }
      }
    }
  `;

  try {
    const result = await graphqlWithAuth(query);
    console.log('=== Basic Query Result ===');
    console.log(`User: ${result.viewer.login}`);
    console.log(`Name: ${result.viewer.name}`);
    console.log(`Bio: ${result.viewer.bio}`);
    console.log(`Total Followers: ${result.viewer.followers.totalCount}`);
    console.log(`Top 5 Repositories:`);
    result.viewer.repositories.edges.forEach((edge) => {
      console.log(`  - ${edge.node.name}: ${edge.node.description}`);
    });
  } catch (error) {
    console.error('Error in basic query:', error.message);
  }
}

/**
 * EXAMPLE 2: Query with Variables
 * Shows how to use variables for dynamic queries
 */
async function exampleQueryWithVariables() {
  const query = `
    query GetRepository($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        name
        description
        url
        stargazerCount
        forkCount
        primaryLanguage {
          name
          color
        }
        issues(first: 3, states: OPEN) {
          totalCount
          edges {
            node {
              number
              title
              state
            }
          }
        }
      }
    }
  `;

  const variables = {
    owner: 'github',
    name: 'docs',
  };

  try {
    const result = await graphqlWithAuth(query, variables);
    console.log('\n=== Query with Variables Result ===');
    console.log(`Repository: ${result.repository.name}`);
    console.log(`Description: ${result.repository.description}`);
    console.log(`Stars: ${result.repository.stargazerCount}`);
    console.log(`Forks: ${result.repository.forkCount}`);
    console.log(`Language: ${result.repository.primaryLanguage?.name || 'N/A'}`);
    console.log(`Open Issues: ${result.repository.issues.totalCount}`);
  } catch (error) {
    console.error('Error in query with variables:', error.message);
  }
}

/**
 * EXAMPLE 3: Aliases
 * Shows how to use aliases to query the same field multiple times with different arguments
 */
async function exampleAliases() {
  const query = `
    query {
      repo1: repository(owner: "facebook", name: "react") {
        name
        stargazerCount
      }
      repo2: repository(owner: "vuejs", name: "vue") {
        name
        stargazerCount
      }
      repo3: repository(owner: "angular", name: "angular") {
        name
        stargazerCount
      }
    }
  `;

  try {
    const result = await graphqlWithAuth(query);
    console.log('\n=== Aliases Example ===');
    console.log(`${result.repo1.name}: ${result.repo1.stargazerCount} stars`);
    console.log(`${result.repo2.name}: ${result.repo2.stargazerCount} stars`);
    console.log(`${result.repo3.name}: ${result.repo3.stargazerCount} stars`);
  } catch (error) {
    console.error('Error in aliases query:', error.message);
  }
}

/**
 * EXAMPLE 4: Fragments
 * Demonstrates reusable fragments to avoid code duplication
 */
async function exampleFragments() {
  const query = `
    fragment RepositoryDetails on Repository {
      name
      description
      url
      stargazerCount
      forkCount
      createdAt
    }

    query {
      react: repository(owner: "facebook", name: "react") {
        ...RepositoryDetails
      }
      vue: repository(owner: "vuejs", name: "vue") {
        ...RepositoryDetails
      }
      svelte: repository(owner: "sveltejs", name: "svelte") {
        ...RepositoryDetails
      }
    }
  `;

  try {
    const result = await graphqlWithAuth(query);
    console.log('\n=== Fragments Example ===');
    const repos = [result.react, result.vue, result.svelte];
    repos.forEach((repo) => {
      console.log(`${repo.name}: ${repo.stargazerCount} ⭐`);
    });
  } catch (error) {
    console.error('Error in fragments query:', error.message);
  }
}

/**
 * EXAMPLE 5: Union Types
 * Demonstrates Union types - SearchResultItem can be Repository, User, or Issue
 * This is a KEY GraphQL principle showing polymorphic types in GitHub's actual schema
 */
async function exampleUnionTypes() {
  const query = `
    query SearchDemoUnion {
      repoSearch: search(query: "language:javascript stars:>10000", type: REPOSITORY, first: 2) {
        edges {
          node {
            __typename
            ... on Repository {
              name
              url
              stargazerCount
            }
            ... on User {
              login
              followers {
                totalCount
              }
            }
          }
        }
      }
      userSearch: search(query: "followers:>1000", type: USER, first: 2) {
        edges {
          node {
            __typename
            ... on User {
              login
              name
              followers {
                totalCount
              }
            }
            ... on Repository {
              name
              stargazerCount
            }
          }
        }
      }
    }
  `;

  try {
    const result = await graphqlWithAuth(query);
    console.log('\n=== Union Types Example (Search Results) ===');
    
    console.log('\nRepositories:');
    result.repoSearch.edges.forEach((edge) => {
      const node = edge.node;
      console.log(`  Type: ${node.__typename}`);
      console.log(`    Name: ${node.name}`);
      console.log(`    URL: ${node.url}`);
    });

    console.log('\nUsers:');
    result.userSearch.edges.forEach((edge) => {
      const node = edge.node;
      console.log(`  Type: ${node.__typename}`);
      console.log(`    Login: ${node.login}`);
      console.log(`    Followers: ${node.followers?.totalCount || 'N/A'}`);
    });
  } catch (error) {
    console.error('Error in union types query:', error.message);
  }
}

/**
 * EXAMPLE 6: Interfaces
 * Demonstrates Interface types - both Issue and PullRequest implement the Closable interface
 * Shows polymorphism through shared interface in GitHub's schema
 */
async function exampleInterfaces() {
  const query = `
    query {
      repository(owner: "github", name: "docs") {
        id
        name
        issues(first: 2, states: OPEN) {
          edges {
            node {
              __typename
              ... on Issue {
                id
                title
                state
                url
              }
            }
          }
        }
        pullRequests(first: 2, states: OPEN) {
          edges {
            node {
              __typename
              ... on PullRequest {
                id
                title
                state
                url
              }
            }
          }
        }
      }
    }
  `;

  try {
    const result = await graphqlWithAuth(query);
    console.log('\n=== Interfaces Example ===');
    const repo = result.repository;
    console.log(`Repository: ${repo.name}`);
    
    console.log('\nOpen Issues:');
    repo.issues.edges.forEach((edge) => {
      console.log(`  [${edge.node.__typename}] ${edge.node.title} (${edge.node.state})`);
      console.log(`    URL: ${edge.node.url}`);
    });

    console.log('\nOpen Pull Requests:');
    repo.pullRequests.edges.forEach((edge) => {
      console.log(`  [${edge.node.__typename}] ${edge.node.title} (${edge.node.state})`);
      console.log(`    URL: ${edge.node.url}`);
    });
  } catch (error) {
    console.error('Error in interfaces query:', error.message);
  }
}

/**
 * EXAMPLE 7: Directives
 * Shows conditional inclusion (@include) and skip (@skip) directives
 * Demonstrates dynamic query behavior based on variables
 */
async function exampleDirectives() {
  const query = `
    query GetUserInfo($includeFollowers: Boolean!, $skipBio: Boolean!) {
      viewer {
        login
        name
        company
        bio @skip(if: $skipBio)
        followers @include(if: $includeFollowers) {
          totalCount
        }
        repositories(first: 3) @include(if: $includeFollowers) {
          totalCount
        }
      }
    }
  `;

  const variables = {
    includeFollowers: true,
    skipBio: false,
  };

  try {
    const result = await graphqlWithAuth(query, variables);
    console.log('\n=== Directives Example (@include/@skip) ===');
    console.log(`User: ${result.viewer.login}`);
    console.log(`Name: ${result.viewer.name}`);
    console.log(`Company: ${result.viewer.company || 'N/A'}`);
    if (result.viewer.bio) {
      console.log(`Bio: ${result.viewer.bio}`);
    }
    if (result.viewer.followers) {
      console.log(`Followers: ${result.viewer.followers.totalCount}`);
      console.log(`Repositories: ${result.viewer.repositories?.totalCount || 0}`);
    }
  } catch (error) {
    console.error('Error in directives query:', error.message);
  }
}

/**
 * EXAMPLE 8: Pagination with Cursor
 * Demonstrates cursor-based pagination for efficient data fetching
 */
async function examplePagination() {
  const query = `
    query GetRepositoriesWithPagination($first: Int!, $after: String) {
      viewer {
        repositories(first: $first, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
          pageInfo {
            hasNextPage
            endCursor
          }
          edges {
            cursor
            node {
              name
              updatedAt
            }
          }
        }
      }
    }
  `;

  const variables = {
    first: 3,
  };

  try {
    const result = await graphqlWithAuth(query, variables);
    console.log('\n=== Pagination Example ===');
    const repos = result.viewer.repositories;
    console.log('Recent Repositories:');
    repos.edges.forEach((edge) => {
      console.log(`  - ${edge.node.name} (updated: ${edge.node.updatedAt})`);
    });
    console.log(`Has Next Page: ${repos.pageInfo.hasNextPage}`);
    if (repos.pageInfo.hasNextPage) {
      console.log(`Next Cursor: ${repos.pageInfo.endCursor}`);
    }
  } catch (error) {
    console.error('Error in pagination query:', error.message);
  }
}

/**
 * EXAMPLE 9: Nested Queries - Deep Field Selection
 * Shows how to nest multiple levels of related data in GitHub's schema
 */
async function exampleNestedQueries() {
  const query = `
    query {
      repository(owner: "github", name: "docs") {
        name
        description
        owner {
          __typename
          login
          ... on User {
            avatarUrl
          }
        }
        defaultBranchRef {
          name
          target {
            ... on Commit {
              oid
              message
              author {
                name
                date
              }
              history(first: 2) {
                edges {
                  node {
                    message
                    committedDate
                  }
                }
              }
            }
          }
        }
      }
    }
  `;

  try {
    const result = await graphqlWithAuth(query);
    console.log('\n=== Nested Queries Example ===');
    const repo = result.repository;
    console.log(`Repository: ${repo.name}`);
    console.log(`Description: ${repo.description}`);
    console.log(`Owner: ${repo.owner.login} (${repo.owner.__typename})`);
    console.log(`Default Branch: ${repo.defaultBranchRef.name}`);
    
    const commit = repo.defaultBranchRef.target;
    if (commit) {
      console.log(`\nLatest Commit:`);
      console.log(`  OID: ${commit.oid.substring(0, 7)}`);
      console.log(`  Message: ${commit.message}`);
      console.log(`  Author: ${commit.author.name}`);
      console.log(`\nRecent Commits:`);
      commit.history.edges.forEach((edge) => {
        console.log(`  - ${edge.node.message.substring(0, 50)}`);
      });
    }
  } catch (error) {
    console.error('Error in nested queries:', error.message);
  }
}

/**
 * EXAMPLE 10: Mutation Example
 * Shows how mutations modify data (addComment mutation on GitHub issues)
 * Note: Uses read-only data for demo safety
 */
async function exampleMutation() {
  // First query to get an issue ID for mutation
  const queryForIssueId = `
    query {
      repository(owner: "github", name: "docs") {
        issues(first: 1, states: OPEN) {
          edges {
            node {
              id
              number
              title
            }
          }
        }
      }
    }
  `;

  // Mutation syntax (not actually executed to avoid side effects)
  const mutationExample = `
    mutation AddCommentToIssue($subjectId: ID!, $body: String!) {
      addComment(input: {
        subjectId: $subjectId
        body: $body
      }) {
        commentEdge {
          node {
            id
            body
            author {
              login
            }
          }
        }
      }
    }
  `;

  try {
    const result = await graphqlWithAuth(queryForIssueId);
    console.log('\n=== Mutation Example (GitHub Issue Comment) ===');
    const firstIssue = result.repository.issues.edges[0]?.node;
    if (firstIssue) {
      console.log(`Issue #${firstIssue.number}: ${firstIssue.title}`);
      console.log(`Issue ID: ${firstIssue.id}`);
      console.log('\nMutation Syntax (for adding a comment):');
      console.log(mutationExample);
      console.log('\nMutation Variables:');
      console.log(JSON.stringify({
        subjectId: firstIssue.id,
        body: "Great issue!"
      }, null, 2));
    }
  } catch (error) {
    console.error('Error in mutation example:', error.message);
  }
}

// Export functions for use in other modules
module.exports = {
  exampleBasicQuery,
  exampleQueryWithVariables,
  exampleAliases,
  exampleFragments,
  exampleUnionTypes,
  exampleInterfaces,
  exampleDirectives,
  examplePagination,
  exampleNestedQueries,
  exampleMutation,
};

// Run examples (uncomment to test)
// (async () => {
//   await exampleBasicQuery();
//   await exampleQueryWithVariables();
//   await exampleAliases();
//   await exampleFragments();
//   await exampleUnionTypes();
//   await exampleInterfaces();
//   await exampleDirectives();
//   await examplePagination();
//   await exampleNestedQueries();
//   await exampleMutation();
// })();
