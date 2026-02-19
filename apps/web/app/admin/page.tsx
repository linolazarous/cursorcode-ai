// apps/web/app/admin/page.tsx
import { redirect } from "next/navigation";
import { getServerSession } from "next-auth/next";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Badge,
  Button,
  Alert,
  AlertDescription,
  AlertTitle,
} from "@cursorcode/ui";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import {
  Users,
  DollarSign,
  CreditCard,
  Zap,
  AlertCircle,
} from "lucide-react";

// Mock data (replace with real API call in production)
const stats = {
  totalUsers: 1248,
  activeSubscriptions: 342,
  monthlyRevenue: 12480,
  totalProjects: 2876,
  failedBuilds: 42,
};

const revenueData = [
  { month: "Jan", revenue: 4200 },
  { month: "Feb", revenue: 5800 },
  { month: "Mar", revenue: 7200 },
  { month: "Apr", revenue: 8900 },
  { month: "May", revenue: 10500 },
  { month: "Jun", revenue: 12480 },
];

const recentUsers = [
  { id: 1, email: "user1@example.com", plan: "pro", joined: "2 hours ago", status: "active" },
  { id: 2, email: "user2@company.io", plan: "premier", joined: "1 day ago", status: "active" },
  { id: 3, email: "test@domain.com", plan: "starter", joined: "3 days ago", status: "pending" },
  { id: 4, email: "dev@startup.dev", plan: "ultra", joined: "1 week ago", status: "active" },
];

export default async function AdminDashboard() {
  const session = await getServerSession(authOptions);

  if (!session?.user?.roles?.includes("admin")) {
    redirect("/dashboard");
  }

  return (
    <div className="min-h-screen storyboard-grid bg-background py-10">
      <div className="container mx-auto px-6 max-w-7xl space-y-12">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
          <div>
            <h1 className="text-display text-5xl font-bold tracking-tighter neon-glow">
              Admin Control Center
            </h1>
            <p className="text-2xl text-muted-foreground mt-2">
              Platform overview • {new Date().toLocaleDateString()}
            </p>
          </div>

          <div className="flex items-center gap-4">
            <Badge variant="outline" className="px-4 py-2 text-sm neon-glow">
              LIVE
            </Badge>
            <Button variant="outline" className="neon-glow">
              Download Full Report
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {[
            { label: "Total Users", value: stats.totalUsers.toLocaleString(), icon: Users, change: "+12% this month" },
            { label: "Active Subscriptions", value: stats.activeSubscriptions.toLocaleString(), icon: CreditCard, change: "78% retention" },
            { label: "Monthly Revenue", value: `\[ {stats.monthlyRevenue.toLocaleString()}`, icon: DollarSign, change: "+18.2% this month" },
            { label: "Total Projects", value: stats.totalProjects.toLocaleString(), icon: Zap, change: `${stats.failedBuilds} failed builds` },
          ].map((stat, i) => (
            <Card key={i} className="cyber-card neon-glow border-brand-blue/30">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">{stat.label}</CardTitle>
                <stat.icon className="h-5 w-5 text-brand-glow" />
              </CardHeader>
              <CardContent>
                <div className="text-4xl font-bold text-foreground tracking-tighter">{stat.value}</div>
                <p className="text-sm text-muted-foreground mt-2">{stat.change}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Tabs */}
        <Tabs defaultValue="overview" className="space-y-8">
          <TabsList className="grid w-full grid-cols-4 bg-card border border-border neon-glow">
            <TabsTrigger value="overview" className="text-lg py-3 data-[state=active]:text-brand-blue">Overview</TabsTrigger>
            <TabsTrigger value="users" className="text-lg py-3 data-[state=active]:text-brand-blue">Users</TabsTrigger>
            <TabsTrigger value="revenue" className="text-lg py-3 data-[state=active]:text-brand-blue">Revenue</TabsTrigger>
            <TabsTrigger value="alerts" className="text-lg py-3 data-[state=active]:text-brand-blue">Alerts</TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-8">
            <div className="grid gap-8 lg:grid-cols-5">
              {/* Revenue Chart */}
              <Card className="lg:col-span-3 cyber-card neon-glow">
                <CardHeader>
                  <CardTitle className="text-display text-3xl">Revenue Trend</CardTitle>
                  <CardDescription>Last 6 months</CardDescription>
                </CardHeader>
                <CardContent className="h-[380px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={revenueData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="month" tick={{ fill: "#94A3B8" }} />
                      <YAxis tick={{ fill: "#94A3B8" }} />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#111827", border: "none", borderRadius: "12px" }}
                        formatter={(value: number) => [` \]{value.toLocaleString()}`, "Revenue"]}
                      />
                      <Bar dataKey="revenue" fill="#1E88E5" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              {/* System Health */}
              <Card className="lg:col-span-2 cyber-card neon-glow">
                <CardHeader>
                  <CardTitle className="text-display text-3xl">System Health</CardTitle>
                  <CardDescription>Real-time platform status</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6 pt-2">
                  {[
                    { label: "API Response Time", value: "142 ms", status: "excellent" },
                    { label: "Grok API Availability", value: "99.98%", status: "excellent" },
                    { label: "Build Queue", value: "4 in queue", status: "normal" },
                    { label: "Error Rate (24h)", value: "0.8%", status: "warning" },
                  ].map((item, i) => (
                    <div key={i} className="flex justify-between items-center py-2 border-b border-border last:border-0">
                      <span className="text-foreground">{item.label}</span>
                      <Badge
                        variant={item.status === "excellent" ? "default" : item.status === "warning" ? "destructive" : "secondary"}
                        className="neon-glow"
                      >
                        {item.value}
                      </Badge>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Users Tab */}
          <TabsContent value="users">
            <Card className="cyber-card neon-glow">
              <CardHeader>
                <CardTitle className="text-display text-3xl">Recent Users</CardTitle>
                <CardDescription>Last 50 sign-ups • Live</CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Email</TableHead>
                      <TableHead>Plan</TableHead>
                      <TableHead>Joined</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {recentUsers.map((user) => (
                      <TableRow key={user.id} className="hover:bg-muted/50">
                        <TableCell className="font-medium">{user.email}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="neon-glow">{user.plan}</Badge>
                        </TableCell>
                        <TableCell>{user.joined}</TableCell>
                        <TableCell>
                          <Badge variant={user.status === "active" ? "default" : "secondary"} className="neon-glow">
                            {user.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="ghost" size="sm" className="neon-glow">View Profile</Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Revenue Tab */}
          <TabsContent value="revenue">
            <Card className="cyber-card neon-glow">
              <CardHeader>
                <CardTitle className="text-display text-3xl">Revenue Breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-6 md:grid-cols-3">
                  {[
                    { title: "This Month", value: "$12,480", change: "+18%" },
                    { title: "Annual Recurring", value: "$148,800", change: "Projected" },
                    { title: "Churn Rate", value: "4.2%", change: "Last 30 days" },
                  ].map((item, i) => (
                    <Card key={i} className="cyber-card border-brand-blue/30">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm text-muted-foreground">{item.title}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="text-4xl font-bold tracking-tighter">{item.value}</div>
                        <p className="text-sm text-brand-glow mt-2">{item.change}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Alerts Tab */}
          <TabsContent value="alerts">
            <Card className="cyber-card neon-glow">
              <CardHeader>
                <CardTitle className="text-display text-3xl">Recent Alerts</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <Alert variant="destructive" className="neon-glow border-red-500/50">
                  <AlertCircle className="h-5 w-5" />
                  <AlertTitle>High Failure Rate Detected</AlertTitle>
                  <AlertDescription>12% of builds failed in the last hour. Check agent logs immediately.</AlertDescription>
                </Alert>

                <Alert className="neon-glow">
                  <AlertCircle className="h-5 w-5 text-brand-blue" />
                  <AlertTitle>Stripe Webhook Delay</AlertTitle>
                  <AlertDescription>Some payment events delayed &gt;5s. Monitoring Render logs.</AlertDescription>
                </Alert>

                <Alert variant="default" className="neon-glow border-brand-blue/50">
                  <Zap className="h-5 w-5 text-brand-glow" />
                  <AlertTitle>Peak Usage Recorded</AlertTitle>
                  <AlertDescription>87 concurrent builds at 14:32 UTC — auto-scaling performed successfully.</AlertDescription>
                </Alert>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
