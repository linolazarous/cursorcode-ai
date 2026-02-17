// packages/db/seed.ts
import { prisma } from './lib/prisma';
import { hashPassword } from './utils';

async function main() {
  console.log('🌱 Seeding database...');

  // Admin User
  const admin = await prisma.user.upsert({
    where: { email: 'admin@cursorcode.ai' },
    update: {},
    create: {
      email: 'admin@cursorcode.ai',
      name: 'CursorCode Admin',
      roles: ['admin'],
      plan: 'ultra',
      credits: 5000,
      totp_enabled: true,
    },
  });

  // Demo User
  const demo = await prisma.user.upsert({
    where: { email: 'demo@cursorcode.ai' },
    update: {},
    create: {
      email: 'demo@cursorcode.ai',
      name: 'Demo User',
      roles: ['user'],
      plan: 'pro',
      credits: 150,
    },
  });

  // Example Projects
  await prisma.project.upsert({
    where: { id: 'proj_demo_1' },
    update: {},
    create: {
      id: 'proj_demo_1',
      title: "AI SaaS Dashboard",
      prompt: "Build a modern AI SaaS dashboard with real-time analytics, user management, and Stripe payments",
      status: "completed",
      userId: demo.id,
      deploy_url: "https://demo.cursorcode.ai",
      preview_url: "https://preview.cursorcode.ai/demo",
      code_repo_url: "https://github.com/cursorcode/demo-saas",
      progress: 100,
      logs: ["✅ Architecture designed", "✅ Code generated", "✅ Deployed to Render"],
    },
  });

  console.log('✅ Seeding completed!');
  console.log(`   Admin: ${admin.email}`);
  console.log(`   Demo User: ${demo.email}`);
}

main()
  .catch((e) => {
    console.error('❌ Seeding failed:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
